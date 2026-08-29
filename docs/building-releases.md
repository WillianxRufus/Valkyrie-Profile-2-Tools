# Building release artifacts

This guide is for maintainers packaging the three applications. End users can
run the published Windows and Linux downloads without Python.

## Linux archives

The Linux release uses the repository's `Dockerfile`, which also runs the
regression suite and release self-checks. From the project root:

```bash
docker build --target artifact --build-arg VERSION=dev-local --output type=local,dest=release .
```

This creates:

- `ValkyrieProfile2-Translator-dev-local-linux-x64.tar.gz`
- `ValkyrieProfile2-CheatPatcher-dev-local-linux-x64.tar.gz`
- `ValkyrieProfile2-VoiceTool-dev-local-linux-x64.tar.gz`

The container uses Ubuntu 24.04, Python 3.11.16, and PyInstaller 6.22.2. It
builds all three applications, runs each frozen binary's `--self-check`, unpacks
each archive, and runs the self-check again.

## Windows archives

PyInstaller does not cross-compile Windows executables from Linux. Use
official 64-bit Python 3.11.9 for Windows with Tkinter and the pinned
PyInstaller version:

```powershell
python -m pip install --disable-pip-version-check "pyinstaller==6.22.2"
python -m unittest discover -s tests -q
python -m PyInstaller data/vp2_release.spec --workpath workspace/internal/build --clean --noconfirm
python -m PyInstaller data/vp2_cheats.spec --workpath workspace/internal/build --clean --noconfirm
python -m PyInstaller data/vp2_voices.spec --workpath workspace/internal/build --clean --noconfirm
.\dist\ValkyrieProfile2-Translator.exe --self-check
.\dist\ValkyrieProfile2-CheatPatcher.exe --self-check
.\dist\ValkyrieProfile2-VoiceTool.exe --self-check
```

Package all three executables using the names in
`.github/workflows/release.yml`, then unpack each archive and run its
`--self-check` before publication.

## Generated packaging files

Local packaging scratch belongs under `workspace/internal/build/`.
PyInstaller's generated analysis and package files must not be written to the
top-level `build/`, which is reserved for completed local ISO outputs.

The exact versions and release steps are pinned in
`.github/workflows/release.yml` and the `Dockerfile`. Update the workflow,
container, this guide, and their regression assertions together when changing
the packaging toolchain.
