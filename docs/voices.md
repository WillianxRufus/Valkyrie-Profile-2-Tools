# Voice tool

ValkyrieProfile2-VoiceTool extracts mapped cutscene voices and
language-dependent samples from a USA or Japanese _Valkyrie Profile 2_ image,
and can put replacement WAVs back into a new image. It never modifies the
source image and does not include game audio.

## Extract voices

In the window, select the USA (`SLUS_214.52`) or Japanese (`SLPM_664.19`)
image, choose a voice root, and select **Extract every voice**. From a source
checkout, the equivalent command is:

```bash
python vp2_voices.py extract <source.iso>
python vp2_voices.py extract <source.iso> -o <voice-root>
```

The default root is `voices/`. USA audio goes under `voices/en/`; Japanese
audio goes under `voices/jp/`. Extraction refuses to merge with an existing
`en/` or `jp/` folder, so a partial or older extraction cannot silently mix
with a new one.

Known cutscene banks are grouped by the scene resource number. The opening,
for example, includes files under:

```text
voices/en/1197/1483-000-8028.wav
voices/en/1197/1485-000-....wav
```

Each name is `<bank>-<subfile>-<clip-id>.wav`. Keep it unchanged: all three
parts identify the exact game slot when the file is patched back. The
adjacent `manifest.csv` records the region, cutscene resource, slot limit,
duration, loudness measurements, and file hash.

## Patch replacement voices

Select the base USA or Japanese image, select any folder containing identified
replacement WAVs, choose the ISO output folder, and select **Patch ISO**. The
folder is searched recursively, so it may be a whole language extraction, one
cutscene folder, or a hand-picked subset.

```bash
python vp2_voices.py patch <base.iso> <replacement-folder>
python vp2_voices.py patch <base.iso> <replacement-folder> -o <output.iso>
```

The default output is `build/<source-name>-voice-patched.iso`. A translated or
cheat-patched USA image can be the base, so subtitles, cheats, and voices can
be combined.

Replacement WAVs must be uncompressed 16-bit, mono PCM at 24000 Hz. A line
must fit its original slot. Overlong audio is rejected by default; shorter
audio is padded with the game's silence frame. A deliberate rough test can
enable **Allow overlong WAVs** in the window or pass `--allow-overlong`,
which trims each tail exactly at the fixed slot boundary.

The older dubbing-kit layout is supported too. A folder such as
`vp2/dub/opening/ptbr-chatterbox` may contain files named only by clip ID,
such as `8028.wav`, when its parent kit has the original `manifest.csv` with
the `bank` and `sub` columns.

## Safety and limits

- Keep the exported file names or the older kit manifest with the audio.
- Do not select a kit root containing English, Japanese, and generated copies
  of the same line together; duplicate targets are rejected.
- Existing ISO outputs are never overwritten by the command line. The window
  asks before replacing an output ISO.
- Existing extraction folders are never overwritten automatically.
- This is fixed-slot replacement. It does not enlarge a line or move voice
  banks, so generated delivery must fit the recorded slot.
