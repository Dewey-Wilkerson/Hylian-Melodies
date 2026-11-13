# Known issues

- Input: gamepad (8BitDo Ultimate 2 Wireless), + / - and the keyboard confirmed by the owner; rumble not yet tested.
- Black around small rooms (castle interiors) is the game's own framing, not a fault.
- Occasional hitches: one 833 ms frame at an early load, a few 50-80 ms frames in a 7-minute session.
- Loading and the splash videos run at 30 fps (the game's own choice while loading; to confirm on hardware).
- No overlay menu (M10); the software keyboard returns the initial text unchanged.
- Restored LAS Recomp renderer code still contains comments and dormant paths about Link's Awakening; the hooks are
  answered "off" (`runtime/nvn/las_feature_stubs.c`). To trim over time.
- SMAA anti-aliasing is not built (not useful for pixel art anyway).
- Audio is measured (docs/audio.md) but not yet checked by ear against the beat; end-to-end latency to the speakers
  is not measured (use the game's calibration).
- The package is built for this machine's CPU level (x86-64-v3 here); build it on the machine that plays it.
