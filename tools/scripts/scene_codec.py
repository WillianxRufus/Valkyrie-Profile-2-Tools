"""Reference-font alphabet and generic VP2 scene-token encoding."""

REFERENCE_FONT_RESOURCE = 33
REFERENCE_FONT_GLYPH_BASE = 0x65

# Glyph slot -> character.  This covers every one-byte slot referenced by the
# USA resource.  The capital letters that exist in this font are S and D.
REFERENCE_FONT_SLOTS = {
    " ": 0,
    "S": 1,
    "o": 2,
    "u": 3,
    "l": 4,
    "t": 5,
    "r": 6,
    "e": 7,
    "D": 8,
    "i": 9,
    "d": 10,
    "y": 11,
    "k": 12,
    "n": 13,
    "w": 14,
    "?": 15,
    "p": 16,
    "a": 17,
    "s": 18,
    "b": 19,
    "m": 20,
    "g": 21,
    "c": 22,
    "h": 23,
    ".": 24,
    "'": 25,
    "v": 26,
}

REFERENCE_CODEPOINTS = {
    character: REFERENCE_FONT_GLYPH_BASE + slot
    for character, slot in REFERENCE_FONT_SLOTS.items()
}
REFERENCE_BY_CODEPOINT = {code: character for character, code in REFERENCE_CODEPOINTS.items()}

REFERENCE_BY_CODEPOINT.update({
    0x0180: "f",
    0x0181: ".",
    0x0182: "I",
    0x0183: "j",
    0x0184: "T",
    0x0185: "P",
    0x0186: "A",
    0x0188: "C",
    0x0189: "W",
    0x018A: "x",
    0x018B: "K",
    0x018C: "B",
    0x018D: "H",
    0x018F: "J",
    0x0190: "z",
    0x0191: "M",
    0x0192: "R",
    0x0193: "O",
    0x0194: "N",
    0x0195: "V",
    0x0196: "E",
    0x0197: "Y",
})
REFERENCE_BY_CODEPOINT.update({
    0x000B: "-",
    0x0018: ",",
})

def pack_tokens(tokens, terminated=True):
    """Encode VP2's one-byte/two-byte glyph token representation."""
    data = bytearray()
    for token in tokens:
        if not 0 <= token <= 0xFFFF:
            raise ValueError("token out of range: 0x%X" % token)
        if token < 0x80:
            data.append(token)
        else:
            data.extend(token.to_bytes(2, "little"))
    if terminated:
        data.append(0)
    return bytes(data)
