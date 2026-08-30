## Issues and Gaps

### Build Time

A full cold build could take up to 30 minutes to complete. Next builds will be warm, and will take around 2 minutes.
The release windows/linux builds have no way around that at the moment.

### Authored Glyphs

Some glyphs are missing, and existing ones could use some polishing.

### Title Screen

The texts in the title screen (New Game, Load Game and Settings) seems to be art.

### Translation Limits and Blockers

Build errors or in-game freezes/crashes can happen if a translated scene goes beyond it's byte headroom.
This is caused by a scene using many different glyphs, line length, and multiple lines going a little over it's original byte size combined
