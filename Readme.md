# Valkyrie Profile 2 Translation Tools

Translate _Valkyrie Profile 2: Silmeria_ (PlayStation 2) into any language. [Showcase](https://trulio2.github.io/Valkyrie-Profile-2-Tools/)

## Requirements

- Python 3.11 or newer
- A USA disc image (`SLUS_214.52`)
- Optionally, the Japanese image (`SLPM_664.19`) for the original script

About 12 GB of free space: the source image, the patched one, and roughly
10 MB of generated tables.

## Use

Download the archive for your platform, unpack it, and open
`ValkyrieProfile2-Translator`. The window guides you through both required
steps: choose your clean USA disc image, prepare the local workspace once,
then choose a language and build the translated ISO. A Japanese image is
optional and adds the original script to the generated reference tables.

The same operations remain available from a terminal for automation and
development:

```bash
# Open the same UI directly from a source checkout.
python vp2_translate.py
```

Or run each step explicitly:

```bash
# Read your disc. Do this once; it takes a couple of minutes.
python vp2_translate.py generate <usa-image.iso>

# Build a translated image.
python vp2_translate.py build <usa-image.iso>
```

The patched image is written to the current directory, or wherever
`--output` says.

To have the original Japanese beside the English in the reference tables,
pass that image too. Order does not matter, and it can be a separate run —
images are recognised by which release they are, and each run remembers
where the others were:

```bash
python vp2_translate.py generate <usa-image.iso> <japanese-image.iso>
```

Choose a language with `--pack`; the default is `translations/pt-BR`.

```bash
python vp2_translate.py build <usa-image.iso> --pack translations/sv-SE
```

## Commands

|                       |                                            |
| --------------------- | ------------------------------------------ |
| `generate <image>...` | read disc images into `workspace/`         |
| `build <image>`       | build a patched image from a language pack |
| `check-pack <pack>`   | validate a language pack                   |
| `--self-check`        | verify an installation is complete         |

Every path option defaults to a location inside the installation, so the
commands work from any directory.

## Build release artifacts locally

The Linux archive is built by the same `Dockerfile` used by the release
workflow. From this directory, run:

```bash
docker build --target artifact --build-arg VERSION=dev-local --output type=local,dest=release .
```

This produces `release/ValkyrieProfile2-Translator-dev-local-linux-x64.tar.gz`
after running the regression suite, language-pack checks, the frozen-binary
self-check, and an archive unpack/self-check round trip. The container fixes
Ubuntu 24.04, the setup-python 3.11.16 toolcache build, and PyInstaller 6.22.2.

A Windows executable must be built on Windows; PyInstaller does not
cross-compile it from Linux. Use official 64-bit Python 3.11.9 with Tk and the
same pinned packager:

```powershell
python -m pip install --disable-pip-version-check "pyinstaller==6.22.2"
python -m unittest discover -s tests -q
python -m PyInstaller data/vp2_release.spec --workpath workspace/internal/build --clean --noconfirm
.\dist\ValkyrieProfile2-Translator.exe --self-check
```

Those versions and commands are pinned in `.github/workflows/release.yml` as
well. Match the workflow's archive naming and run a final unpack/self-check
when preparing a file for publication.

Local packaging scratch belongs under `workspace/internal/build/`:
`local-release/` for an optional native tool environment and `vp2_release/`
for PyInstaller's generated analysis and package files. Neither belongs under
the top-level `build/`, which remains available for completed local outputs.

## Translating

Write into `translations/<locale>/`. Each row is a record identity and your
text; the English and Japanese sit in `workspace/reference/`, which is
generated and never committed.

Adding a language: copy an existing pack directory, change `pack.toml`, and
clear the `translated` column. See
[docs/translation-format.md](docs/translation-format.md).

`glossary/` lists the game's names — characters, items, places, abilities —
beside their translations, so a term reads the same everywhere it appears.

A character no release drew — `ã`, `å`, `ł` — is drawn by the project rather
than taken from a disc. See
[docs/authoring-glyphs.md](docs/authoring-glyphs.md).

## Contributing

[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md).

## License

GPL-3.0-only. What that covers, and what it does not, is in
[legal/LICENSE-SCOPE.md](legal/LICENSE-SCOPE.md).

Nothing here contains game data. The tools read your disc image, write the
tables they need beside themselves, and produce a patched image.
