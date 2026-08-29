# Voice tool

ValkyrieProfile2-VoiceTool extracts every voice bank from a USA or Japanese
_Valkyrie Profile 2_ image and can put replacement WAVs back into a new image.
It never modifies the source image and does not include game audio.

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
adjacent `manifest.csv` records the region, cutscene resource and voice-scene
number where known, slot limit, duration, loudness measurements, and file
hash.

The scene records contain 79 distinct voice-scene groups. Their slot spans
match 79 voice banks exactly, including interleaved late-numbered scenes such
as voice scene 1170 in bank 1482. All 79 are grouped by resource and the tool
checks each mapped bank's clip count while extracting. The six banks that are
not referenced by a scene (1520, 1523, 1525, 1541, 1559, and 1562) remain
under `unmapped/` rather than being mislabeled as cutscene or battle audio.
Their file names are still fully patchable.

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
be combined. The boot release and VP2 resource index are checked before the
ISO is copied.

Replacement WAVs must be uncompressed 16-bit, mono PCM at 24000 Hz. A line
must fit its original `max_seconds` slot. Overlong audio is rejected by
default; shorter audio is padded with the game's silence frame. A deliberate
rough test can enable **Allow overlong WAVs** in the window or pass
`--allow-overlong`, which trims each tail exactly at the fixed slot boundary.
The tool
preserves the bank table, SEQW headers, allocations, disc index, ISO size, and
every byte outside the selected payload slots, then reads every replacement
back from disk before completing the output.

The older dubbing-kit layout is supported too. A folder such as
`vp2/dub/opening/ptbr-chatterbox` may contain files named only by clip ID,
such as `8028.wav`, when its parent kit has the original `manifest.csv` with
the `bank` and `sub` columns. The historical `opening/ptbr-chatterbox` set has
several overlong lines and therefore needs the explicit trimming option to
reproduce its older patched build.

## Safety and limits

- Keep the exported file names or the older kit manifest with the audio.
- Do not select a kit root containing English, Japanese, and generated copies
  of the same line together; duplicate targets are rejected.
- Existing ISO outputs are never overwritten by the command line. The window
  asks before replacing an output ISO.
- Existing extraction folders are never overwritten automatically.
- This is fixed-slot replacement. It does not enlarge a line or move voice
  banks, so generated delivery must fit the recorded slot.
