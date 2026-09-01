## Issues and Gaps

### Build Time

A full cold build could take up to 30 minutes to complete. Next builds will be warm, and will take around 2 minutes.
The release windows/linux builds have no way around that at the moment.

### Authored Glyphs

Some glyphs are missing, and existing ones could use some polishing.

### Title Screen

The texts in the title screen (New Game, Load Game and Settings) seems to be art.

### Translation Limits and Blockers

A scene has a limited amount of space. Going past it causes a build error,
or a freeze in game. Long lines add to it, but the main cost is the number
of _different_ accented letters a scene uses.

`python test.py <language> <resource>` says whether a scene still fits and
how much room is left, without building an ISO. See the
[translator guide](translator.md).
