#!/usr/bin/env python3
"""tri-Ace PS2 bigfile unpacker (Star Ocean 3 / Radiata Stories / Valkyrie Profile 2)."""
import os, sys, struct, csv, collections

SECTOR = 0x800
MASK = 0xFFFFFFFF
GAMES = {  # name: (seed, signature, table_offset, total_entries)
    "VP2": (0x49287491, 0x516F6699, 0x00200000, 0x0C00),
    "SO3": (0x13578642, 0x27D51556, 0x00200000, 0x1800),
    "RS":  (0x13578642, 0x27D51556, 0x3C6C1800, 0x1200),
}
MAGIC = {0x464C457F: "elf", 0x005A4C53: "slz", 0x015A4C53: "slz", 0x025A4C53: "slz",
         0x035A4C53: "slz", 0x00454C53: "sle", 0x01454C53: "sle", 0x02454C53: "sle",
         0x03454C53: "sle", 0x00534C5A: "zls", 0x57514553: "seq", 0x4B434150: "pac",
         0x73696854: "txt", 0x00594D44: "dmy", 0x6D336F73: "mc", 0x7370636D: "mc",
         0x27D51556: "idx", 0x516F6699: "idx", 0x67225277: "unk", 0x73646F4B: "kod",
         0x00504352: "rcp", 0x00534946: "fis", 0x00435243: "crc"}


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def load_table(f):
    for name, (seed, sig, tbl, total) in GAMES.items():
        f.seek(tbl)
        head = f.read(4)
        if len(head) == 4 and struct.unpack("<I", head)[0] == sig:
            break
    else:
        raise RuntimeError("No tri-Ace index table found (unsupported ISO).")
    f.seek(tbl)
    raw = f.read(total * 3 * 4)
    t = list(struct.unpack("<%dI" % (total * 3), raw))
    key = seed
    for i in range(total):
        t[0 * total + i] ^= key; key = (key ^ ((key << 1) & MASK)) & MASK
        t[1 * total + i] ^= key; key = (key ^ (~seed & MASK)) & MASK
        t[2 * total + i] ^= key; key = (key ^ ((key << 2) & MASK) ^ seed) & MASK
    t[0] = tbl // SECTOR
    return name, total, t


def classify(buf, length):
    hdr = u32(buf, 0)
    if hdr == 0:
        t1, t2 = u32(buf, 4), u32(buf, 8)
        if t1 == 0 and t2 == 0x10: return "010"
        if t1 == 0 and t2 == 0x00: return "000"
        if (16 * ((t1 + 1) & MASK)) & MASK == t2 and u32(buf, 0x1C) == t2: return "pk1"
        return "bin"
    if hdr == 0x20: return "020"
    if hdr < 0x100:
        t1 = t2 = 0
        for j in range(hdr):
            a = struct.unpack_from("<H", buf, 4 + 4 * j)[0]
            b = struct.unpack_from("<H", buf, 6 + 4 * j)[0]
            c = struct.unpack_from("<H", buf, 8 + 4 * j)[0]
            t1, t2 = a, b
            if a + b != c: break
        if (t1 + t2) * SECTOR == length: return "pk2"
        return "bin"
    if u32(buf, 0x14) == length: return "pk3"
    return MAGIC.get(hdr, "bin")


def entries(f, total, t):
    for i in range(total):
        lba, secs = t[i], t[total + i]
        if secs:
            yield i, lba * SECTOR, secs * SECTOR


def cmd_manifest(iso):
    with open(iso, "rb") as f:
        name, total, t = load_table(f)
        print("game=%s  entries=%d" % (name, total))
        tally = collections.Counter()
        rows = []
        for i, off, length in entries(f, total, t):
            f.seek(off)
            buf = f.read(min(0x1000, length))
            if len(buf) < 0x20:
                buf = buf + b"\x00" * 0x20
            kind = classify(buf, length)
            tally[kind] += 1
            rows.append((i, off, length, kind))
        csv_path = iso + ".triace.csv"
        with open(csv_path, "w", newline="") as cf:
            w = csv.writer(cf); w.writerow(["index", "byte_offset", "length", "type"])
            w.writerows(rows)
        print("type tally:", ", ".join("%s=%d" % (k, v) for k, v in tally.most_common()))
        print("manifest -> %s" % csv_path)
        for kind in ("seq", "pk1", "pk2", "020", "pac"):
            big = sorted((r for r in rows if r[3] == kind), key=lambda r: -r[2])[:5]
            if big:
                print("  biggest .%s: " % kind + ", ".join("#%d(%.1fMB)" % (r[0], r[2] / 1e6) for r in big))


def cmd_unpack(iso, outdir, types, max_mb):
    os.makedirs(outdir, exist_ok=True)
    want = set(types.split(",")) if types else None
    limit = max_mb * 1024 * 1024 if max_mb else None
    with open(iso, "rb") as f:
        name, total, t = load_table(f)
        n = 0
        for i, off, length in entries(f, total, t):
            f.seek(off)
            head = f.read(min(0x1000, length))
            if len(head) < 0x20:
                head = head + b"\x00" * 0x20
            kind = classify(head, length)
            if want and kind not in want:
                continue
            if limit and length > limit:
                continue
            f.seek(off)
            with open(os.path.join(outdir, "%04d.%s" % (i, kind)), "wb") as o:
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(remaining, 1 << 20))
                    if not chunk: break
                    o.write(chunk); remaining -= len(chunk)
            n += 1
        print("extracted %d files -> %s" % (n, outdir))


def main():
    a = sys.argv
    if len(a) >= 3 and a[1] == "manifest":
        cmd_manifest(a[2])
    elif len(a) >= 4 and a[1] == "unpack":
        types = a[a.index("--type") + 1] if "--type" in a else None
        max_mb = int(a[a.index("--max-mb") + 1]) if "--max-mb" in a else None
        cmd_unpack(a[2], a[3], types, max_mb)
    else:
        print(__doc__); sys.exit(1)


if __name__ == "__main__":
    main()
