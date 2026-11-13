# Known issues

- Input: a real gamepad works (8BitDo Ultimate 2 Wireless: A, B, X, L, R, ZL, ZR, d-pad and combinations reached
  the game in a 2-minute hands-on run). Not yet confirmed by hand: + / -, the sticks, the keyboard, rumble.
- The image drawn shrunk into the window's top-left at moments was seen with the old "match the window" render
  scale; not seen since the native default (2026-11-13). Watch for it.
- Loading and the splash videos run at 30 fps (the game's own choice while loading; to confirm on hardware).
- No overlay menu (M10); the software keyboard returns the initial text unchanged.
- Restored LAS Recomp renderer code still contains comments and dormant paths about Link's Awakening; the hooks are
  answered "off" (`runtime/nvn/las_feature_stubs.c`). To trim over time.
- SMAA anti-aliasing is not built (not useful for pixel art anyway).
- Audio is measured (docs/audio.md) but not yet checked by ear against the beat; end-to-end latency to the speakers
  is not measured (use the game's calibration).
