# Contributing

Contributions to the tools, tests, documentation and language packs are
welcome.

By submitting one you agree to license it under `GPL-3.0-only`, the same as
the project, and confirm you have the right to do so. Copyright stays with
each contributor.

## Before opening a pull request

```bash
python -m unittest discover -s tests -q
python vp2_translate.py check-pack <locale>
```

## What must not be committed

- disc images, executables, save states, or anything extracted from them;
- the game's **script** — dialogue, menu labels, system messages: the text a
  language pack refers to by identity rather than quoting;
- fonts, glyph bitmaps, graphics, audio or caches taken from a release;
- anything generated into `workspace/`, `build/` or `dist/`.

Two things that look like exceptions and are not.

**Glyph bitmaps the project drew** are tracked, in
`data/authored-glyphs.csv` and `data/authored-marks.csv`. The line is where
the pixels came from, not what they are.

**The glossary** carries names — characters, items, places, skills,
sealstones — in English, Japanese and translation. Translating consistently
means knowing what a term already was, and a term is a name rather than
expression: the entries run about a dozen characters and the longest is
thirty. Extending it is fine; turning it into sentences is not. The moment
an entry is a line someone speaks, it is script and belongs in a pack as an
identity.

## Language packs

A pack row is a record identity and your text. Keep the identity columns as
generated; `check-pack` verifies them.

Adding a language: copy an existing pack, change `pack.toml`, clear the
`translated` column, and reduce `build-profile.csv` to the resources you mean
to translate — a build writes what that file names and nothing else. Format
details are in [translation-format.md](translation-format.md).

A translation may be your own expression while still being based on a
third-party work — you license only the rights you hold, and no license here
grants rights to the game itself. A translation imported from elsewhere
needs the agreement of everyone whose work it retains.

## Glyphs

Adding a character no release drew is a supported contribution and needs no
font editor: [authoring-glyphs.md](authoring-glyphs.md).
