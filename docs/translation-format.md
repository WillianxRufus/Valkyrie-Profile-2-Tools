# Translation-pack format

A format-2 language pack mirrors the generated translator reference without
publishing the game's source script.

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
CSV, and neither does a patcher flag: those live in `build-profile.csv`.
Complete blank rows are intentional: they make each language tree line up with
the local reference and expose untranslated coverage without copying source
text.

## Build profile

`build-profile.csv` is the one file in a pack that is not translation. It
lists the resources this language's build writes, one row each:

```csv
kind,resource,sheet,flags,verify
```

- `kind` is `scene`, `container`, or `fontless`.
- `resource` is the resource the build patches.
- `sheet` is the generated record sheet its text comes from. Several
  resources may name one sheet: the menu layout points 25, 868, 869, 1480,
  and 1481 at `container-0024.csv`.
- `flags` asks for font work — `full-font` re-cuts a scene's own face,
  `shared-font-glyphs` adds characters to a shared one.
- `verify` reads the resource back out of the finished image.

A build only touches what this file names, so a pack translating one menu
lists one resource and finishes in seconds. Rows carrying no translation are
still meaningful: the shared-font containers hold the face that other
resources draw with, and dropping them leaves accented characters blank
everywhere.

## Local reference

`vp2_translate.py generate` writes the ignored `workspace/reference/` tree
with the same filenames, identities, and row order. Its CSVs add
`original_en`, optional `original_jp`, and context such as speaker, scene line,
chapter number, occurrence count, and affected resources. Translators open the
reference file and the matching language file side by side, but edit only the
tracked language file.

Everything not intended for translators remains under `workspace/internal/`,
including inventories, caches, full normalized records, and generation
metadata. Its subpaths are tool-owned implementation details. Both workspace
folders are derived from user-supplied images and ignored by Git.

## Menu units

Menu text is highly duplicated, and identical English labels can require
different translations in different contexts. The tracked, source-free
`data/menu-layout.csv` maps each menu translation unit to its exact container
records. Reference menu rows show one representative `resource/message_id`,
an occurrence count, and the affected resources. The builder expands that one
authored translation only to the exact records assigned to the unit.

This avoids duplicate work while preserving contextual variants such as short
labels and battle-specific wording.

`data/menu-layout.csv` is order-sensitive: the first row of each unit is the
identity a pack keys on, so rows may be appended but must not be reordered.

## Validation rules

`check-pack` rejects:

- English, Japanese, or equivalent source columns;
- extra or missing CSV columns;
- paths outside `chapter.csv`, `dialogue/`, and the five `menu/` files;
- a dialogue filename whose resource disagrees with its rows;
- duplicate stable identities; and
- an unsupported pack format.

Compatibility with the supported USA game revision is a builder-level check,
not translator-authored metadata. Japanese reference extraction is optional
and is never required to build a translated USA image.
