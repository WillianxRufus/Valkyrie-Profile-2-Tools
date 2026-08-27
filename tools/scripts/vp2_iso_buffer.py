"""Hold the full ISO bytes in memory and own the tri-Ace index."""
import ctypes
import io
import os
import sys

from . import triace_ps2_unpack as triace


def copy_image(source, destination, progress=None):
    """Copy a whole disc image, reporting integer percentages."""
    total = os.path.getsize(source)

    def report(done):
        if progress and total:
            progress(min(100, int(done * 100 / total)))

    if sys.platform == "win32":
        try:
            return _copy_image_win32(source, destination, total, report)
        except (OSError, AttributeError, ValueError):
            pass
    report(0)
    with open(source, "rb") as reader, open(destination, "wb") as writer:
        done = 0
        chunk = 1 << 24
        while True:
            block = reader.read(chunk)
            if not block:
                break
            writer.write(block)
            done += len(block)
            report(done)
    return destination


_COPY_CALLBACK = ctypes.WINFUNCTYPE(
    ctypes.c_uint,          # return: PROGRESS_CONTINUE
    ctypes.c_longlong,      # TotalFileSize
    ctypes.c_longlong,      # TotalBytesTransferred
    ctypes.c_longlong,      # StreamSize
    ctypes.c_longlong,      # StreamBytesTransferred
    ctypes.c_ulong,         # dwStreamNumber
    ctypes.c_ulong,         # dwCallbackReason
    ctypes.c_void_p,        # hSourceFile
    ctypes.c_void_p,        # hDestinationFile
    ctypes.c_void_p,        # lpData
) if sys.platform == "win32" else None


def _copy_image_win32(source, destination, total, report):
    """``CopyFileExW`` with a progress routine; raises OSError on failure."""
    kernel32 = ctypes.windll.kernel32

    def callback(total_size, transferred, _ss, _st, _num, _reason,
                 _src, _dst, _data):
        report(transferred)
        return 0  # PROGRESS_CONTINUE

    report(0)
    routine = _COPY_CALLBACK(callback)
    ok = kernel32.CopyFileExW(
        ctypes.c_wchar_p(os.fspath(source)),
        ctypes.c_wchar_p(os.fspath(destination)),
        routine, None, None, ctypes.c_ulong(0))
    if not ok:
        raise ctypes.WinError()
    report(total)
    return destination


class IsoBuffer:
    """In-memory ISO buffer for single-pass build."""

    __slots__ = ("bytes", "_table", "_total", "is_in_memory")

    def __init__(self, iso_bytes):
        if isinstance(iso_bytes, bytearray):
            self.bytes = iso_bytes
        elif isinstance(iso_bytes, (bytes, memoryview)):
            self.bytes = bytearray(iso_bytes)
        else:
            raise TypeError(
                "iso_bytes must be bytes, bytearray, or memoryview; "
                "got %r" % type(iso_bytes).__name__)
        _name, self._total, self._table = triace.load_table(io.BytesIO(self.bytes))
        self.is_in_memory = False

    @classmethod
    def from_path(cls, path):
        """Load an ISO from disk into a new ``IsoBuffer``."""
        size = os.path.getsize(path)
        buffer = bytearray(size)
        with open(path, "rb") as handle:
            read = handle.readinto(buffer)
        if read != size:
            raise ValueError("read %d of %d bytes from %s"
                             % (read, size, path))
        return cls(buffer)

    def commit(self, path):
        """Serialise the in-memory bytes back to disk."""
        with open(path, "wb") as handle:
            handle.write(self.bytes)

    @property
    def total(self):
        """Number of tri-Ace entries (files + the table itself)."""
        return self._total

    @property
    def table(self):
        """The decoded tri-Ace index (length 3*total; read-only view)."""
        return self._table

    def entry_byte_offset(self, resource):
        """Byte offset of entry *resource* in the ISO."""
        return self._table[resource] * triace.SECTOR

    def entry_outer_allocation(self, resource):
        """Outer allocation of entry *resource*, in bytes."""
        return self._table[self._total + resource] * triace.SECTOR

    def read_entry(self, resource):
        """Return the raw entry bytes (length = outer allocation)."""
        sectors = self._table[self._total + resource]
        if not sectors:
            return b""
        byte_offset = self._table[resource] * triace.SECTOR
        return bytes(self.bytes[byte_offset:byte_offset + sectors * triace.SECTOR])

    def write_entry(self, resource, new_bytes):
        """Splice *new_bytes* into the buffer at the entry's byte offset."""
        if not isinstance(new_bytes, (bytes, bytearray)):
            raise TypeError(
                "new_bytes must be bytes or bytearray; "
                "got %r" % type(new_bytes).__name__)
        byte_offset = self._table[resource] * triace.SECTOR
        allocation = self._table[self._total + resource] * triace.SECTOR
        if len(new_bytes) > allocation:
            raise ValueError(
                "entry %d: new_bytes (%d) exceeds outer allocation (%d); "
                "the patcher must shrink to fit or grow into trailing "
                "slack before calling write_entry" %
                (resource, len(new_bytes), allocation))
        self.bytes[byte_offset:byte_offset + len(new_bytes)] = bytes(new_bytes)
        return new_bytes


class IsoFile:
    """File-backed twin of :class:`IsoBuffer`, for builds that must not"""

    __slots__ = ("path", "readonly", "_handle", "_table", "_total",
                 "is_in_memory")

    def __init__(self, path, mode="r+b"):
        if mode not in ("r+b", "rb"):
            raise ValueError("mode must be 'r+b' or 'rb'; got %r" % (mode,))
        self.path = os.path.abspath(path)
        self.readonly = mode == "rb"
        self._handle = open(self.path, mode)
        _name, self._total, self._table = triace.load_table(self._handle)
        self.is_in_memory = False

    @classmethod
    def from_path(cls, path, mode="r+b"):
        """Mirror of ``IsoBuffer.from_path``, so callers can swap classes."""
        return cls(path, mode)

    def close(self):
        if self._handle is not None and not self._handle.closed:
            self._handle.flush()
            self._handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False

    @property
    def total(self):
        """Number of tri-Ace entries (files + the table itself)."""
        return self._total

    @property
    def table(self):
        """The decoded tri-Ace index (length 3*total; read-only view)."""
        return self._table

    def entry_byte_offset(self, resource):
        """Byte offset of entry *resource* in the ISO."""
        return self._table[resource] * triace.SECTOR

    def entry_outer_allocation(self, resource):
        """Outer allocation of entry *resource*, in bytes."""
        return self._table[self._total + resource] * triace.SECTOR

    def read_entry(self, resource):
        """Return the raw entry bytes (length = outer allocation)."""
        sectors = self._table[self._total + resource]
        if not sectors:
            return b""
        self._handle.seek(self._table[resource] * triace.SECTOR)
        want = sectors * triace.SECTOR
        data = self._handle.read(want)
        if len(data) != want:
            raise ValueError(
                "entry %d: read %d of %d bytes from %s -- the image is "
                "shorter than its index claims"
                % (resource, len(data), want, self.path))
        return data

    def write_entry(self, resource, new_bytes):
        """Write *new_bytes* at the entry's byte offset."""
        if self.readonly:
            raise ValueError(
                "%s is open read-only; open it 'r+b' to patch" % self.path)
        if not isinstance(new_bytes, (bytes, bytearray)):
            raise TypeError(
                "new_bytes must be bytes or bytearray; "
                "got %r" % type(new_bytes).__name__)
        allocation = self._table[self._total + resource] * triace.SECTOR
        if len(new_bytes) > allocation:
            raise ValueError(
                "entry %d: new_bytes (%d) exceeds outer allocation (%d); "
                "the patcher must shrink to fit or grow into trailing "
                "slack before calling write_entry" %
                (resource, len(new_bytes), allocation))
        self._handle.seek(self._table[resource] * triace.SECTOR)
        self._handle.write(bytes(new_bytes))
        return new_bytes

    def commit(self, path=None):
        """Flush the handle; the bytes are already where they belong."""
        if path is not None and os.path.abspath(path) != self.path:
            raise ValueError(
                "IsoFile is backed by %s and cannot commit to %s; open the "
                "output path directly instead of copying the image"
                % (self.path, os.path.abspath(path)))
        self._handle.flush()
        os.fsync(self._handle.fileno())
