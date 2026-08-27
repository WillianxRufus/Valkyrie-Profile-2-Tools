#!/usr/bin/env python3
"""tri-Ace SLZ compressor (modes 1 and 2) — produces game-valid blobs that"""
import argparse
import sys, struct
import os
import hashlib
from . import slz
from .paths import CACHE_ROOT, DATA_DIR

MIN_MATCH, MAX_MATCH, MAX_DIST, MAX_CHAIN = 3, 18, 4095, 4096
MIN_RUN, MAX_RUN = 4, 0xFF + 0x13

_ENCODER_VERSION = 1
_DEFAULT_CACHE_DIR = os.path.join(os.fspath(CACHE_ROOT), "slz")
_TRACKED_CACHE_DIR = os.path.join(os.fspath(DATA_DIR), "slz-cache")


def _rle_length(src, pos):
    """Return the mode-2 encodable length of the repeated byte at *pos*."""
    end = min(len(src), pos + MAX_RUN)
    value = src[pos]
    length = 1
    while pos + length < end and src[pos + length] == value:
        length += 1
    return length


def compress_body(src, mode=1):
    if mode == 3:
        return compress_body_mode3(src)
    if mode not in (1, 2):
        raise ValueError("only SLZ modes 1, 2 and 3 can be compressed")

    n = len(src)
    head = {}
    prev = [-1] * n

    def insert(pos):
        if pos + 3 <= n:
            key = src[pos:pos + 3]
            prev[pos] = head.get(key, -1)
            head[key] = pos

    tokens = []
    i = 0
    while i < n:
        best_len, best_dist = 0, 0
        max_match = 17 if mode == 2 else MAX_MATCH
        maxlen = min(max_match, n - i)
        if maxlen >= MIN_MATCH:
            cand = head.get(src[i:i + 3], -1)
            limit = i - MAX_DIST
            chain = 0
            while cand >= 0 and cand >= limit and chain < MAX_CHAIN:
                if src[cand + best_len] == src[i + best_len]:  # quick reject
                    l = 0
                    while l < maxlen and src[cand + l] == src[i + l]:
                        l += 1
                    if l > best_len:
                        best_len, best_dist = l, i - cand
                        if l == maxlen:
                            break
                cand = prev[cand]
                chain += 1
        run_len = _rle_length(src, i) if mode == 2 else 0
        if run_len >= MIN_RUN and run_len >= best_len:
            tokens.append(("run", src[i], run_len))
            end = i + run_len
            while i < end:
                insert(i); i += 1
        elif best_len >= MIN_MATCH:
            tokens.append(("match", best_dist, best_len))
            end = i + best_len
            while i < end:
                insert(i); i += 1
        else:
            tokens.append(("literal", src[i]))
            insert(i); i += 1

    out = bytearray()
    for k in range(0, len(tokens), 8):
        grp = tokens[k:k + 8]
        flag = 0
        body = bytearray()
        for bit, t in enumerate(grp):
            if t[0] == "literal":
                flag |= (1 << bit)
                body.append(t[1])
            elif t[0] == "match":
                _, dist, length = t
                body.append(dist & 0xFF)
                body.append(((dist >> 8) & 0x0F) | (((length - 3) & 0x0F) << 4))
            else:
                _, fill, length = t
                if length <= 18:
                    body.extend((fill, 0xF0 | (length - 3)))
                else:
                    body.extend((length - 0x13, 0xF0, fill))
        out.append(flag)
        out.extend(body)
    return bytes(out)


def _match_table(src, max_match, max_chain=MAX_CHAIN):
    """Longest match and its distance at every position, via hash chains."""
    n = len(src)
    head, prev = {}, [-1] * n
    best_len = bytearray(n)
    best_dist = [0] * n
    for i in range(n):
        if i + MIN_MATCH > n:
            break
        key = src[i:i + MIN_MATCH]
        cand = head.get(key, -1)
        limit = i - MAX_DIST
        length, distance, chain = 0, 0, 0
        maxlen = min(max_match, n - i)
        while cand >= 0 and cand >= limit and chain < max_chain:
            if src[cand + length] == src[i + length]:
                l = 0
                while l < maxlen and src[cand + l] == src[i + l]:
                    l += 1
                if l > length:
                    length, distance = l, i - cand
                    if l == maxlen:
                        break
            cand = prev[cand]
            chain += 1
        best_len[i], best_dist[i] = length, distance
        prev[i] = head.get(key, -1)
        head[key] = i
    return best_len, best_dist


def _run_table(src):
    n = len(src)
    runs = [0] * n
    for i in range(n - 1, -1, -1):
        if i + 1 < n and src[i] == src[i + 1] and runs[i + 1] < MAX_RUN:
            runs[i] = runs[i + 1] + 1
        else:
            runs[i] = 1
    return runs


def compress_body_optimal(src, mode=1):
    """Shortest-path parse over the same token set the greedy encoder uses."""
    if mode not in (1, 2):
        raise ValueError("only SLZ modes 1 and 2 can be compressed")
    n = len(src)
    max_match = 17 if mode == 2 else MAX_MATCH
    best_len, best_dist = _match_table(src, max_match)
    runs = _run_table(src) if mode == 2 else None

    cost = [0] * (n + 1)
    choice = [None] * (n + 1)
    for i in range(n - 1, -1, -1):
        value = cost[i + 1] + 9
        pick = ("literal", src[i], 1)
        length = best_len[i]
        if length >= MIN_MATCH:
            distance = best_dist[i]
            for l in range(MIN_MATCH, length + 1):
                alt = cost[i + l] + 17
                if alt < value:
                    value, pick = alt, ("match", distance, l)
        if runs is not None and runs[i] >= MIN_RUN:
            for l in range(MIN_RUN, runs[i] + 1):
                alt = cost[i + l] + (17 if l <= 18 else 25)
                if alt < value:
                    value, pick = alt, ("run", src[i], l)
        cost[i], choice[i] = value, pick

    tokens, i = [], 0
    while i < n:
        kind, payload, length = choice[i]
        tokens.append((kind, payload) if kind == "literal"
                      else (kind, payload, length))
        i += length
    return _emit(tokens)


def compress_body_exact_size(src, mode, target_size):
    """Encode *src* as exactly ``target_size`` body bytes."""
    if mode not in (1, 2):
        raise ValueError("exact-size compression supports SLZ modes 1 and 2")
    if target_size < 1:
        raise ValueError("exact compressed body size must be positive")
    src = bytes(src)
    size = len(src)
    max_match = 17 if mode == 2 else MAX_MATCH
    best_len, best_dist = _match_table(src, max_match)
    runs = _run_table(src) if mode == 2 else None
    reachable = [[0] * 8 for _ in range(size + 1)]
    reachable[0][0] = 1
    cost_mask = (1 << (target_size + 1)) - 1

    for position in range(size):
        for phase, costs in enumerate(reachable[position]):
            if not costs:
                continue
            next_phase = (phase + 1) & 7
            control = 1 if phase == 0 else 0
            reachable[position + 1][next_phase] |= (
                costs << (1 + control)) & cost_mask
            for length in range(MIN_MATCH, best_len[position] + 1):
                reachable[position + length][next_phase] |= (
                    costs << (2 + control)) & cost_mask
            if runs is not None:
                for length in range(MIN_RUN, runs[position] + 1):
                    payload = 2 if length <= 18 else 3
                    reachable[position + length][next_phase] |= (
                        costs << (payload + control)) & cost_mask

    end_phases = [phase for phase in range(8)
                  if (reachable[size][phase] >> target_size) & 1]
    if not end_phases:
        raise ValueError("cannot encode %d bytes as exactly %d compressed "
                         "body bytes in SLZ mode %d" %
                         (size, target_size, mode))

    position, phase, cost = size, end_phases[0], target_size
    reverse_tokens = []
    while position:
        previous_phase = (phase - 1) & 7
        control = 1 if previous_phase == 0 else 0
        choice = None

        for length in range(min(max_match, position), MIN_MATCH - 1, -1):
            previous = position - length
            edge_cost = 2 + control
            if (best_len[previous] >= length and cost >= edge_cost and
                    (reachable[previous][previous_phase] >>
                     (cost - edge_cost)) & 1):
                choice = (previous,
                          ("match", best_dist[previous], length),
                          cost - edge_cost)
                break
        if choice is None and runs is not None:
            for length in range(min(MAX_RUN, position), MIN_RUN - 1, -1):
                previous = position - length
                edge_cost = (2 if length <= 18 else 3) + control
                if (runs[previous] >= length and cost >= edge_cost and
                        (reachable[previous][previous_phase] >>
                         (cost - edge_cost)) & 1):
                    choice = (previous, ("run", src[previous], length),
                              cost - edge_cost)
                    break
        if choice is None:
            previous = position - 1
            edge_cost = 1 + control
            if (cost >= edge_cost and
                    (reachable[previous][previous_phase] >>
                     (cost - edge_cost)) & 1):
                choice = (previous, ("literal", src[previous]),
                          cost - edge_cost)
        if choice is None:
            raise AssertionError("failed to reconstruct exact SLZ parse")
        position, token, cost = choice
        phase = previous_phase
        reverse_tokens.append(token)

    body = _emit(list(reversed(reverse_tokens)))
    if len(body) != target_size:
        raise AssertionError("exact SLZ parse has the wrong size")
    return body


def _emit(tokens):
    out = bytearray()
    for k in range(0, len(tokens), 8):
        grp = tokens[k:k + 8]
        flag = 0
        body = bytearray()
        for bit, t in enumerate(grp):
            if t[0] == "literal":
                flag |= (1 << bit)
                body.append(t[1])
            elif t[0] == "match":
                _, dist, length = t
                body.append(dist & 0xFF)
                body.append(((dist >> 8) & 0x0F) | (((length - 3) & 0x0F) << 4))
            else:
                _, fill, length = t
                if length <= 18:
                    body.extend((fill, 0xF0 | (length - 3)))
                else:
                    body.extend((length - 0x13, 0xF0, fill))
        out.append(flag)
        out.extend(body)
    return bytes(out)


UNIT = 2
M3_MIN_UNITS, M3_MAX_UNITS, M3_MAX_DIST = 2, 17, 4095


def _match_table_units(src, max_chain=MAX_CHAIN):
    n = len(src) // UNIT
    head, prev = {}, [-1] * n
    best_len = [0] * n
    best_dist = [0] * n
    for i in range(n):
        if i + M3_MIN_UNITS > n:
            break
        at = i * UNIT
        key = src[at:at + M3_MIN_UNITS * UNIT]
        cand = head.get(key, -1)
        limit = i - M3_MAX_DIST
        length, distance, chain = 0, 0, 0
        maxlen = min(M3_MAX_UNITS, n - i)
        while cand >= 0 and cand >= limit and chain < max_chain:
            base = cand * UNIT
            # quick reject on the unit that would extend the current best
            if length == 0 or src[base + length * UNIT] == src[at + length * UNIT]:
                l = 0
                while (l < maxlen and
                       src[base + l * UNIT] == src[at + l * UNIT] and
                       src[base + l * UNIT + 1] == src[at + l * UNIT + 1]):
                    l += 1
                if l > length:
                    length, distance = l, i - cand
                    if l == maxlen:
                        break
            cand = prev[cand]
            chain += 1
        best_len[i], best_dist[i] = length, distance
        prev[i] = head.get(key, -1)
        head[key] = i
    return best_len, best_dist


def compress_body_mode3(src, max_chain=MAX_CHAIN):
    """Encode LZSS16.  Every token costs the same, so fewest tokens wins."""
    if len(src) % UNIT:
        raise ValueError("SLZ mode 3 encodes whole 16-bit units; "
                         "input length %d is odd" % len(src))
    n = len(src) // UNIT
    best_len, best_dist = _match_table_units(src, max_chain)

    cost = [0] * (n + 1)
    choice = [None] * (n + 1)
    for i in range(n - 1, -1, -1):
        value = cost[i + 1] + 1
        pick = (0, 1)
        length = best_len[i]
        if length >= M3_MIN_UNITS:
            distance = best_dist[i]
            for l in range(M3_MIN_UNITS, length + 1):
                alt = cost[i + l] + 1
                if alt < value:
                    value, pick = alt, (distance, l)
        cost[i], choice[i] = value, pick

    tokens, i = [], 0
    while i < n:
        distance, length = choice[i]
        tokens.append((distance, length, i))
        i += length

    out = bytearray()
    for k in range(0, len(tokens), 16):
        group = tokens[k:k + 16]
        flags = 0
        body = bytearray()
        for bit, (distance, length, position) in enumerate(group):
            if distance == 0:
                flags |= (1 << bit)
                body.extend(src[position * UNIT:position * UNIT + UNIT])
            else:
                body.append(distance & 0xFF)
                body.append(((distance >> 8) & 0x0F) | ((length - 2) << 4))
        out.append(flags & 0xFF)
        out.append((flags >> 8) & 0xFF)
        out.extend(body)
    return bytes(out)


def _cache_key(src, mode, optimal, target_size):
    """SHA-256 over (encoder version, mode, optimal, target_size, src)."""
    h = hashlib.sha256()
    h.update(_ENCODER_VERSION.to_bytes(2, "little"))
    h.update(int(mode).to_bytes(1, "little"))
    h.update(b"\x01" if optimal else b"\x00")
    if target_size is None:
        h.update(b"\xff\xff\xff\xff")
    else:
        h.update(int(target_size).to_bytes(4, "little"))
    h.update(bytes(src))
    return h.hexdigest()


def _cache_path(cache_dir, key):
    # Shard by the first two hex chars so a few thousand entries do not land
    # in one directory.  NTFS handles it; this just keeps `ls` cheap.
    return os.path.join(cache_dir, key[:2], key + ".slz")


def _read_cache(cache_dir, key):
    try:
        with open(_cache_path(cache_dir, key), "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _write_cache(cache_dir, key, blob):
    path = _cache_path(cache_dir, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, path)


def _trace_cache_key(key):
    """Record one used key as a race-safe empty marker when tracing is on."""
    trace_dir = os.environ.get("VP2_SLZ_CACHE_TRACE")
    if not trace_dir:
        return
    os.makedirs(trace_dir, exist_ok=True)
    path = os.path.join(trace_dir, key)
    try:
        with open(path, "xb"):
            pass
    except FileExistsError:
        pass


def _resolve_cache_dir(explicit):
    if explicit is not None:
        return explicit
    env = os.environ.get("VP2_SLZ_CACHE")
    if env == "0":
        return ""
    if env:
        return env
    return _DEFAULT_CACHE_DIR


def _compress_uncached(src, mode=1, optimal=True, target_size=None):
    if mode == 3:
        body = compress_body_mode3(src)
        return (b"SLZ" + bytes([mode]) + struct.pack("<I", len(body))
                + struct.pack("<I", len(src)) + struct.pack("<I", 0))  + body
    if target_size is not None:
        body = compress_body_exact_size(src, mode, target_size)
    else:
        body = (compress_body_optimal(src, mode) if optimal
                else compress_body(src, mode))
    hdr = b"SLZ" + bytes([mode]) + struct.pack("<I", len(body)) \
        + struct.pack("<I", len(src)) + struct.pack("<I", 0)
    return hdr + body


def compress(src, mode=1, optimal=True, target_size=None, *, cache_dir=None):
    """Compress *src* to a full SLZ blob (header + body)."""
    src = bytes(src)
    active_dir = _resolve_cache_dir(cache_dir)
    if not active_dir:
        return _compress_uncached(src, mode=mode, optimal=optimal,
                                  target_size=target_size)
    key = _cache_key(src, mode, optimal, target_size)
    cached = (_read_cache(_TRACKED_CACHE_DIR, key)
              if cache_dir is None else None)
    if cached is None:
        cached = _read_cache(active_dir, key)
    if cached is not None:
        _trace_cache_key(key)
        return cached
    blob = _compress_uncached(src, mode=mode, optimal=optimal,
                              target_size=target_size)
    _write_cache(active_dir, key, blob)
    _trace_cache_key(key)
    return blob


def main():
    parser = argparse.ArgumentParser(description="compress a file to tri-Ace SLZ")
    parser.add_argument("--mode", type=int, choices=(1, 2, 3), default=1,
                        help="SLZ mode (default: 1; 3 is LZSS16)")
    parser.add_argument("--test", action="store_true",
                        help="round-trip the input instead of writing an output")
    parser.add_argument("input")
    parser.add_argument("output", nargs="?")
    args = parser.parse_args()

    if args.test:
        if args.output is not None:
            parser.error("--test accepts one input file, not an output file")
        src = open(args.input, "rb").read()
        blob = compress(src, args.mode)
        back = slz.decompress(blob)
        ok = back == src
        print("mode %d: input %d -> compressed %d (%.1f%%), round-trip %s"
              % (args.mode, len(src), len(blob),
                 100.0 * len(blob) / max(1, len(src)),
                 "OK" if ok else "*** MISMATCH ***"))
        sys.exit(0 if ok else 2)
    if args.output is None:
        parser.error("an output path is required unless --test is used")
    src = open(args.input, "rb").read()
    open(args.output, "wb").write(compress(src, args.mode))
    print("wrote %s (mode %d)" % (args.output, args.mode))


if __name__ == "__main__":
    main()
