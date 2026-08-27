# Glyph-name fingerprints

The releases store several text faces as indexes into font bitmaps rather than
as Unicode. `en.csv` and `jp.csv` describe ordinary local text faces;
`title.csv` describes the separate chapter-title display face. These tables
contain only the project-authored identification of each bitmap fingerprint: a
SHA-1 digest and the character a human identified from that glyph.

They do not contain bitmap pixels, game text, resource bytes, or extracted font
data. The local workspace generator fingerprints glyphs extracted from the
user's image and joins them to these names. Unknown fingerprints remain
explicitly undecoded rather than being guessed.
