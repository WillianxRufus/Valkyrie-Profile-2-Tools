# Translator guide

ValkyrieProfile2-Translator builds a translated copy of the USA release of
_Valkyrie Profile 2: Silmeria_. It reads the source disc image and writes a
separate ISO; it never changes the source.

## Using the window

Open `ValkyrieProfile2-Translator` from a downloaded release, or run this from
a source checkout:

```bash
python vp2_translate.py
```

Then:

1. Select a clean USA image (`SLUS_214.52`).
2. Optionally select the Japanese image (`SLPM_664.19`). This adds Japanese
   text to the generated reference files but is not required for a build.
3. Select a language and output folder.
4. Choose **Build translated ISO**.

The application identifies each selected disc before starting. The first
build generates a local workspace from the source image and may take several
minutes. Later builds reuse that workspace.

## Command line

The source launcher supports these commands:

| Command                                                    | Purpose                                                                    |
| ---------------------------------------------------------- | -------------------------------------------------------------------------- |
| `python vp2_translate.py`                                  | Open the window.                                                           |
| `python vp2_translate.py generate <image>...`              | Prepare the local workspace and reference files.                           |
| `python vp2_translate.py build <usa-image.iso> [language]` | Build a translated ISO.                                                    |
| `python vp2_translate.py check-pack <language>`            | Validate a language pack.                                                  |
| `python vp2_translate.py --self-check`                     | Check that an installation contains its required files and window runtime. |

`generate` is optional because `build` runs it automatically when the
workspace has not been prepared. To include both English and Japanese in the
local reference:

```bash
python vp2_translate.py generate <usa-image.iso> <japanese-image.iso>
```

The default language is `pt-BR`. Supply another locale from `translations/`
or a path to a language pack:

```bash
python vp2_translate.py build <usa-image.iso> sv-SE
python vp2_translate.py build <usa-image.iso> <path-to-language-pack>
```

Use `--workspace` with `generate` or `build` to change the workspace location.
Use `--output` with `build` to choose the output file:

```bash
python vp2_translate.py build <usa-image.iso> pt-BR --output <translated.iso>
```

Run any command with `--help` for its complete arguments.

## Output and workspace

When running from source, the default output is
`build/<source-name>.<locale>.iso`. Generated files live under `workspace/`:

- `workspace/reference/` contains the English reference and, when supplied,
  the Japanese reference for translators.
- `workspace/internal/` contains generated build state and caches owned by the
  tool.

Both directories are derived from user-supplied images and are ignored by
Git. A build reads its completed image back to verify translated resources
unless the command-line-only `--no-verify` option is used.

## Language packs

Language packs live under `translations/<locale>/`. Each pack decides which
resources its build changes, so small packs can build much faster than a full
translation.

For the file layout and validation rules, see
[translation-format.md](translation-format.md). For contributing translations
or a new language, see [CONTRIBUTING.md](CONTRIBUTING.md). If a translation
needs a character unavailable in the shipped fonts, see
[authoring-glyphs.md](authoring-glyphs.md).
