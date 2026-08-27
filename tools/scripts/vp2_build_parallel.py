"""Per-row parallelism for the build driver."""

import hashlib
import multiprocessing
import os
import shutil
import sys
import time
from pathlib import Path


from .paths import TOOLS_DIR

HERE = TOOLS_DIR

from . import vp2_iso_buffer as iso_buffer
from . import vp2_shared_font as shared_font


PREINSTALL_FILENAME = "preinstall.iso"   # legacy; caches hold entries now
PREINSTALL_ENTRIES_DIRNAME = "entries"

DEFAULT_JOBS_CAP = 16


WORKER_PEAK_MULTIPLE = 2.0


def jobs_that_fit(iso_bytes, cap=DEFAULT_JOBS_CAP, reserve=0.15,
                  peak=WORKER_PEAK_MULTIPLE):
    """How many workers this machine's free memory can actually hold."""
    free = _available_memory()
    if not free or not iso_bytes:
        return cap
    usable = free * (1.0 - reserve) - iso_bytes
    if usable <= 0:
        return 1
    return max(1, min(cap, int(usable // (iso_bytes * peak))))


def _available_memory():
    """Free physical memory in bytes, or ``None`` if it cannot be read."""
    try:
        if sys.platform == "win32":
            import ctypes

            class _Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            status = _Status()
            status.dwLength = ctypes.sizeof(_Status)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(
                    ctypes.byref(status)):
                return None
            return int(status.ullAvailPhys)
        return (os.sysconf("SC_AVPHYS_PAGES")
                * os.sysconf("SC_PAGE_SIZE"))
    except Exception:                                     # noqa: BLE001
        return None


_PATCHERS = {}


def _register_patchers():
    """Populate ``_PATCHERS`` with the real patchers from vp2_build."""
    if _PATCHERS:
        return
    from .vp2_build import (
        patch_container_resource_in_memory,
        patch_scene_resource_in_memory,
        patch_fontless_resource_in_memory,
    )
    _PATCHERS["container"] = patch_container_resource_in_memory
    _PATCHERS["worldmap"] = patch_fontless_resource_in_memory
    _PATCHERS["fontless"] = patch_fontless_resource_in_memory
    _PATCHERS["scene"] = patch_scene_resource_in_memory


def _source_fingerprint(path):
    """Stable fingerprint of the source ISO that the install depends on."""
    st = os.stat(path)
    return f"{st.st_size:x}-{int(st.st_mtime):x}"


def _chars_fingerprint(chars):
    """SHA the sorted chars set; the install result depends only on this"""
    return hashlib.sha1(
        "".join(sorted(chars)).encode("utf-8")).hexdigest()[:16]


def get_or_build_preinstall(
    source_iso_path, rows, cache_root, *, force=False, verbose=True,
):
    """Return ``{resource: bytes}`` -- the entries the shared-font"""
    from .vp2_build import collect_shared_font_characters

    needed = collect_shared_font_characters(rows)
    cache_root = Path(cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    src_fp = _source_fingerprint(source_iso_path)
    chars_fp = _chars_fingerprint(needed) if needed else "none"
    cache_dir = cache_root / f"{src_fp}-{chars_fp}"
    entries_dir = cache_dir / PREINSTALL_ENTRIES_DIRNAME

    if entries_dir.is_dir() and not force:
        entries = {int(p.stem): p.read_bytes()
                   for p in sorted(entries_dir.glob("*.bin"))}
        if verbose:
            print(f"preinstall: cache hit ({cache_dir.name}, "
                  f"{len(entries)} entry/entries)")
        return entries

    if verbose:
        print(
            f"preinstall: building "
            f"(src={src_fp}, chars={''.join(sorted(needed)) or 'none'})"
        )
    entries = {}
    if needed:
        # Read-only, so only entry 8 is ever pulled off the disc.
        with iso_buffer.IsoFile(str(source_iso_path), "rb") as iso:
            original = iso.read_entry(shared_font.SHARED_FONT_ENTRY)
        rebuilt, info = shared_font.install_glyphs(
            original, needed, shared_font.SHARED_EXTENSION_TOKENS
        )
        if not info.get("no_op"):
            entries[shared_font.SHARED_FONT_ENTRY] = bytes(rebuilt)
            if verbose:
                print("preinstall: " + shared_font.describe_install(info))
        elif verbose:
            print("preinstall: entry 8 already had all requested chars")

    entries_dir.mkdir(parents=True, exist_ok=True)
    for stale in entries_dir.glob("*.bin"):
        stale.unlink()
    for resource, data in entries.items():
        (entries_dir / f"{resource}.bin").write_bytes(data)
    return entries


def apply_preinstall(iso, entries):
    """Lay the cached install over an image, in place."""
    for resource, data in sorted((entries or {}).items()):
        iso.write_entry(resource, data)
    return iso


def partition_rows_round_robin(rows, jobs):
    """Split ``rows`` into ``jobs`` slices in manifest order."""
    if jobs < 1:
        raise ValueError(f"jobs must be >= 1, got {jobs}")
    slices = [[] for _ in range(jobs)]
    for i, row in enumerate(rows):
        slices[i % jobs].append((i, row))
    return [s for s in slices if s]


def _worker_process(source_path, preinstall_entries, rows_with_index,
                    primary_lookup=None):
    """Module-level worker entry point."""
    _register_patchers()

    iso = apply_preinstall(
        iso_buffer.IsoBuffer.from_path(source_path), preinstall_entries)
    results = []
    for manifest_index, row in rows_with_index:
        kind = row["kind"]
        resource = int(row["resource"])
        row_start = time.time()
        if kind not in _PATCHERS:
            raise ValueError(
                f"row {manifest_index + 1}: unknown kind {kind!r}; "
                f"known: {sorted(_PATCHERS)}"
            )
        _PATCHERS[kind](iso, row, primary_lookup=primary_lookup)
        entry_bytes = bytes(iso.read_entry(resource))
        results.append(
            (manifest_index, resource, entry_bytes,
             time.time() - row_start)
        )
    return results


def merge_writes(
    source_path, preinstall_entries, worker_results, rows, *,
    output_path, verbose=True,
):
    """Stream the source to ``output_path`` and lay every write over it."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(source_path), str(output_path))
    writes_applied = 0
    with iso_buffer.IsoFile(str(output_path)) as iso:
        apply_preinstall(iso, preinstall_entries)
        flat = [item for result in worker_results for item in result]
        flat.sort(key=lambda t: t[0])
        for manifest_index, resource, entry_bytes, row_seconds in flat:
            iso.write_entry(resource, entry_bytes)
            writes_applied += 1
            if verbose:
                row = rows[manifest_index]
                print(
                    f"  [{manifest_index + 1}/{len(rows)}] "
                    f"{row['kind']} {row['resource']}: "
                    f"applied ({len(entry_bytes)} bytes, "
                    f"{row_seconds:.1f}s)"
                )
        iso.commit()
    return writes_applied


def run_parallel(
    source_iso_path,
    output_iso_path,
    rows,
    *,
    jobs,
    cache_root,
    force_preinstall=False,
    verbose=True,
    primary_lookup=None,
    _initializer=None,
    _initargs=None,
):
    """Drive a parallel build."""
    started = time.time()

    preinstall_entries = get_or_build_preinstall(
        str(source_iso_path),
        rows,
        cache_root,
        force=force_preinstall,
        verbose=verbose,
    )

    slices = partition_rows_round_robin(rows, jobs)
    if not slices:
        merge_writes(source_iso_path, preinstall_entries, [], rows,
                     output_path=output_iso_path, verbose=False)
        if verbose:
            print("parallel: empty manifest; copied source -> output")
        return

    if verbose:
        print(
            f"parallel: {len(rows)} row(s) across {len(slices)} worker(s) "
            f"({len(preinstall_entries)} preinstalled entry/entries)"
        )

    ctx = multiprocessing.get_context("spawn")
    worker_results = []
    pool_kwargs = {"processes": len(slices)}
    if _initializer is not None:
        pool_kwargs["initializer"] = _initializer
        pool_kwargs["initargs"] = _initargs or ()
    with ctx.Pool(**pool_kwargs) as pool:
        async_results = [
            pool.apply_async(
                _worker_process,
                (str(source_iso_path), preinstall_entries, slice_,
                 primary_lookup)
            )
            for slice_ in slices
        ]
        for slice_index, ar in enumerate(async_results):
            try:
                worker_results.append(ar.get())
            except Exception as exc:
                rows_text = "; ".join(
                    f"row #{idx + 1} {row['kind']} {row['resource']}"
                    for idx, row in slices[slice_index]
                )
                raise RuntimeError(
                    f"parallel worker {slice_index} failed "
                    f"({type(exc).__name__}: {exc}); "
                    f"rows in slice: {rows_text}"
                ) from exc

    writes_applied = merge_writes(
        source_iso_path, preinstall_entries, worker_results, rows,
        output_path=output_iso_path, verbose=verbose,
    )

    out = Path(output_iso_path)
    elapsed = time.time() - started
    if verbose:
        print(
            f"parallel: {writes_applied} write(s) in {elapsed:.1f}s -> "
            f"{out}"
        )
