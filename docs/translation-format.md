# Translation-pack format

A language pack mirrors the translator reference without publishing the game's
source script.

```text
translations/<locale>/
  pack.toml
  build-profile.csv
  chapter.csv
  dialogue/
    scene-XXXX.csv
    container-0010.csv
  menu/
    menu-1.csv
    menu-2.csv
    menu-3.csv
    menu-4.csv
    menu-5.csv
```

`pack.toml` declares `format = 2`, a BCP 47 `locale`, and a display `name`.
Every translation CSV has exactly these columns:

```csv
resource,message_id,translated,notes
```

- `resource` and `message_id` are generated stable identities. Do not edit
  them.
- `translated` is the authored target text. It may be blank.
- `notes` contains only contributor-authored information safe to publish.

The path supplies the record family, so `kind` is not repeated in every row.
No source text, source hash, or extraction detail belongs in a translation
CSV. Complete blank rows are intentional: they make each language tree line up
with the local reference and expose untranslated coverage without copying
source text.

## Build profile

`build-profile.csv` lists the resources this language's build writes, one row
each. Its `kind` is `scene`, `container`, or `fontless`. A build only touches
what this file names, so a pack translating one menu lists one resource and
finishes in seconds.

## Menu units

Menu text is highly duplicated, and identical English labels can require
different translations in different contexts. The pack's menu files use one
row per distinct unit, and the builder expands that translation to every
matching record.

## Validation

`check-pack` rejects English or Japanese source columns, extra or missing CSV
columns, paths outside the pack's `chapter.csv`, `dialogue/`, and `menu/`
files, dialogue filenames whose resource disagrees with their rows, and
duplicate stable identities.

A translated build only works on the supported USA game revision; the build
itself checks compatibility.
