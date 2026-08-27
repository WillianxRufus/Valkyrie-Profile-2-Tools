"""Generic bitmap helpers for VP2 scene-font glyphs."""

def glyph_value(block, x, y):
    if not (0 <= x < 32 and 0 <= y < 28):
        return 0
    position = y * 32 + x
    return (block[position // 2] >> (4 * (position & 1))) & 0x0F


def set_glyph_value(block, x, y, value):
    if not (0 <= x < 32 and 0 <= y < 28):
        return
    position = y * 32 + x
    byte_index = position // 2
    shift = 4 * (position & 1)
    block[byte_index] = (
        block[byte_index] & ~(0x0F << shift)) | ((value & 0x0F) << shift)


def draw_mark(block, points):
    """Draw a small fill/outline/antialias mark using VP2's palette indexes."""
    centers = set(points)
    # Index 15 is the bright body, 7 the dark outline, and 3 its soft edge in
    # the existing local glyphs.  Never erase the base letter under a mark.
    for x, y in centers:
        for dx, dy, value in ((-1, 0, 7), (1, 0, 7), (0, -1, 7), (0, 1, 7),
                              (-1, -1, 3), (1, -1, 3), (-1, 1, 3), (1, 1, 3)):
            px, py = x + dx, y + dy
            if (px, py) not in centers and glyph_value(block, px, py) == 0:
                set_glyph_value(block, px, py, value)
    for x, y in centers:
        set_glyph_value(block, x, y, 15)


def accented_block(source, mark, vertical_shift=0):
    block = bytearray(source)
    if mark == "acute_dotless":
        # The original i dot touches the stem's antialiasing in the texture.
        # Remove its complete upper component before adding the acute mark.
        for y in range(12):
            for x in range(24):
                set_glyph_value(block, x, y, 0)
        mark = "acute"
    occupied = [(x, y) for y in range(28) for x in range(24)
                if glyph_value(block, x, y)]
    if not occupied:
        raise ValueError("cannot accent an empty glyph")
    left = min(x for x, _ in occupied)
    right = max(x for x, _ in occupied)
    center = (left + right) // 2
    top = min(y for _, y in occupied)
    if mark == "acute":
        core = [(center - 1, top - 3), (center, top - 4), (center + 1, top - 5)]
        points = core + [(x + 1, y) for x, y in core]
    elif mark == "grave":
        # Mirror the acute: same weight and clearance, descending toward
        # the letter instead of away from it.
        core = [(center + 1, top - 3), (center, top - 4), (center - 1, top - 5)]
        points = core + [(x + 1, y) for x, y in core]
    elif mark == "acute_upper":
        core = [(center - 1, top - 3), (center, top - 4), (center + 1, top - 5)]
        points = core + [(x + 1, y) for x, y in core]
    elif mark == "tilde":
        wave_top = top - 3
        tilde_stamp = (
            ((-2, 0, 1), (-1, 0, 1), (0, 0, 1), (1, 0, 1), (2, 0, 1)),
            ((-5, 1, 3), (-4, 1, 15), (-3, 1, 15), (-2, 1, 15), (-1, 1, 15),
             (0, 1, 15), (1, 1, 15), (2, 1, 15), (3, 1, 15), (4, 1, 15),
             (5, 1, 3)),
            ((-5, 2, 1), (-4, 2, 7), (-3, 2, 7), (-2, 2, 7), (-1, 2, 7),
             (0, 2, 7), (1, 2, 7), (2, 2, 7), (3, 2, 7), (4, 2, 7),
             (5, 2, 1)),
        )
        for row in tilde_stamp:
            for dx, dy, value in row:
                px, py = center + dx, wave_top + dy
                if 0 <= px < 32 and 0 <= py < 28 and glyph_value(block, px, py) == 0:
                    set_glyph_value(block, px, py, value)
        # Stamp replaces draw_mark; skip the points/draw_mark path below.
        return bytes(block)
    elif mark == "circumflex":
        core = [(center - 2, top - 3), (center - 1, top - 4), (center, top - 5),
                (center + 1, top - 4), (center + 2, top - 3)]
        points = core + [(x, y + 1) for x, y in core]
    elif mark == "cedilla":
        core = [(center, 23), (center + 1, 24), (center + 1, 25),
                (center, 26), (center - 1, 27)]
        points = [(x - 1, y) for x, y in core]
    else:
        raise ValueError("unknown accent mark: %s" % mark)
    horizontal_shift = 1 if mark in ("tilde", "circumflex", "cedilla") else 2
    points = [(x + horizontal_shift, y + vertical_shift) for x, y in points]
    draw_mark(block, points)
    return bytes(block)
