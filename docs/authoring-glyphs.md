# Drawing glyphs

A language usually needs characters no release of the game drew. Adding one
needs a checkout, Python, and the disc image you already build from.

## The face

A glyph is a 32×28 cell of 4-bit pixels: sixteen ink levels, `0` transparent
and `15` full. Every stroke in the face is built the same way — a bright core
about three pixels across, a flat mid-tone halo one pixel out each side, and
one pixel of antialiasing. A lowercase `l` shows it whole:

```
.37BFD75      edge 3 | halo 7 | core B F D | halo 7 | edge 5
```

A letter therefore uses twelve to fourteen of the sixteen levels, with about
a tenth of its ink at full. Anything far off that reads as pasted on:

```bash
python -m tools.scripts.glyph_face_check reference
python -m tools.scripts.glyph_face_check check data/authored-marks.csv
python -m tools.scripts.glyph_face_check show data/authored-marks.csv ç
```

`check` must report **0 off-face**.

## Composing a character from an existing mark

Most additions are one line. `COMPOSITES` in
`tools/scripts/vp2_glyph_compose.py` maps a character to a base letter, a
mark, and where the mark goes:

```python
"ä": ("a", "ü", "above"),      # a, with the diaeresis
"ñ": ("n", "ã", "above"),      # n, with the tilde
"ì": ("i", "à", "replace"),    # the mark replaces the i's tittle
```

The mark is named by the character it was drawn for: `ü` means the
diaeresis, `ã` the tilde. The body comes from whichever font the game is
using at that point, so the result is in the right face automatically.

`above` and `below` stack; `replace` is for `i`, whose dot sits where an
accent wants to be.

## Drawing a mark that does not exist

Marks are centrelines, not bitmaps. Add one to `SHAPES` in
`tools/scripts/author_accent_marks.py`:

```python
"ring": {
    "rows": range(4, 10),           # the rows it may ink
    "path": [[(6.4, 5.2), (8.0, 6.6), (6.4, 8.0), (4.8, 6.6), (6.4, 5.2)]],
    "weight": 0.85,                 # below 1 draws thinner
},
```

- **`path`** — polylines in cell coordinates, where a whole number is a
  pixel's centre. Several polylines for a mark in separate pieces, like the
  diaeresis.
- **`rows`** — ink outside this band is dropped.
- **`weight`** — scales the whole profile, so the mark stays the same shape.
  A chevron puts two strokes where one usually goes, so the circumflex is
  drawn lighter than the acute.
- **`cap`** — above 1 squares off a stroke's ends instead of letting them
  fade. Rarely needed.
- **`taper`**, **`widths`** — vary core brightness and width along a stroke,
  for a display face rather than the subtitle one.

Point a donor key at the shape in `DONOR_SHAPES`, then:

```bash
python -m tools.scripts.author_accent_marks --check    # preview and measure
python -m tools.scripts.author_accent_marks --write    # write the table
```

Two things to know while iterating. A mark's apparent size is its **bright
core**, not its ink box — shorten the path before touching the weight. And a
wave needs roughly twice its own stroke thickness of amplitude, or crest and
trough merge into a bar.

## Placing a mark

The composer centres a mark's ink box over the letter's and pins its
**bottom** row a fixed distance above the letter. Shrinking the `rows` band
therefore slides a mark _down_ into the letter rather than making it
smaller; narrow the path instead.

Two tables in `vp2_glyph_compose.py` adjust the rest:

- `MARK_VERTICAL_SHIFTS` — negative raises, positive lowers.
- `MARK_HORIZONTAL_SHIFTS` — positive moves right.

Both are keyed by the mark, so one entry fixes every character using it.

Horizontal shifts may be **fractional**, and often should be. The game
carries more than one cut of the face and they differ by a pixel — the
shared codepage `a` is one column wider than a scene font's — so centring
the same mark rounds differently on each. A whole pixel moves both; half a
pixel moves only the one that was rounding the other way:

```python
MARK_HORIZONTAL_SHIFTS = {"ã": 0.5}   # scene font moves 1; shared font does not
```

## Drawing a whole letter

When there is nothing to compose from, the letter goes in
`data/authored-glyphs.csv` with its full 448-byte bitmap. Match the face by
hand — core, halo, edge — and check it the same way.

## The chapter-title face

Chapter titles use a second, ornate face whose accents are calligraphic
rather than geometric, and it is unfinished: the build derives what it can.
Improving it is a good contribution. Its measurements:

- 14 ink levels, 14% of ink at full, against the subtitle face's 14 and 10%
- its stem reads `37BFFB73` where the subtitle stem reads `37BFD75`
- its letters fill the cell, so a title accent overlaps the letter's top
- width and core taper on separate curves

```python
ORNATE = ((0.0, 15.0), (0.8, 15.0), (1.9, 7.0), (4.2, 7.0), (5.3, 0.0))
grid = render(path, rows, weight=1.0, profile=ORNATE,
              widths=[(0.0, 0.55), (0.2, 1.0), (0.8, 1.0), (1.0, 0.5)],
              taper=[(0.0, 0.0), (0.7, 1.0), (1.0, 0.0)])
```

## Before opening a pull request

```bash
python -m unittest discover -s tests -q
python vp2_translate.py build <your-image.iso>
```

Then look at it in an emulator, and say which characters you checked. A mark
two pixels out of place patches, verifies, and reads back correctly; only a
person can see it.

Draw glyphs, or derive them from an image supplied at build time. Do not
commit pixels copied out of any release — the test suite checks for it.
