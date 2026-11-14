# Known issues

- Input: gamepad (8BitDo Ultimate 2 Wireless), + / - and the keyboard confirmed by the owner; rumble not yet tested.
- Black around small rooms (castle interiors) is the game's own framing, not a fault.
- Occasional hitches during loads: the 833 ms one was the game's own work loading an area (827 ms of game CPU);
  a few 50-80 ms frames are loads too, two were our render thread (texture work). Not pursued further.
- `show_fps = 1` shows the frame rate in the window title (not checked by eye yet).
- The window has no icon of its own; desktops show the menu entry's icon through the app id (`hylian-melodies`).
- Loading and the splash videos run at 30 fps (the game's own choice while loading; to confirm on hardware).
- No overlay menu (M10); the software keyboard returns the initial text unchanged.
- Restored LAS Recomp renderer code still contains comments and dormant paths about Link's Awakening; the hooks are
  answered "off" (`runtime/nvn/las_feature_stubs.c`). To trim over time.
- SMAA anti-aliasing is not built (not useful for pixel art anyway).
- Audio is measured (docs/audio.md) but not yet checked by ear against the beat; end-to-end latency to the speakers
  is not measured (use the game's calibration).
- The game is built for x86-64-v2 by default, so a build runs on other x86-64 machines; `HM_MARCH=v3 makepkg` (or
  `--march v3|native`) optimizes for the building computer, and that copy refuses to start on an older CPU.
- Packages built before r25 (`0.1.0.r25.g089a5d2`) may hold an older executable than their version says (the setup
  resumed "compile already done"; fixed). Rebuild with `makepkg -f`.
- The menu's scaling-filter change takes effect at the next start (the filter is built into the present shader).
