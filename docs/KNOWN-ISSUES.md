# Known issues

- Input: gamepad (8BitDo Ultimate 2 Wireless), + / - and the keyboard confirmed by the owner; rumble not yet tested.
- Black around small rooms (castle interiors) is the game's own framing, not a fault.
- Occasional hitches during loads: the 833 ms one was the game's own work loading an area (827 ms of game CPU);
  a few 50-80 ms frames are loads too, two were our render thread (texture work). Not pursued further.
- `show_fps = 1` shows the frame rate in the window title (not checked by eye yet).
- The window has no icon of its own; desktops show the menu entry's icon through the app id (`hylian-melodies`).
- Loading and the splash videos run at 30 fps (the game's own choice while loading; to confirm on hardware).
- The software keyboard returns the initial text unchanged.
- LAS Recomp's renderer still carries parts made for its 3D game that this port does not need or has not judged
  yet: the per-draw tint and mirror flip in translated shaders, the
  present shader's colour filter, dynamic resolution and FSR, the ambient-occlusion and shadow special cases, and
  many comments that point at files of LAS Recomp's tree (`renderer.m`, `metal.m`, issue numbers). Its hooks into
  Link's Awakening features, the in-place reboot, SMAA and the `audren:u` mixer were removed 2026-11-14
  (docs/PROGRESS.md). Removing the rest changes shader text or behaviour and needs a run of the game each time.
- Audio is measured (docs/audio.md) but not yet checked by ear against the beat; end-to-end latency to the speakers
  is not measured (use the game's calibration).
- The game is built for x86-64-v2 by default, so a build runs on other x86-64 machines; `HM_MARCH=v3 makepkg` (or
  `--march v3|native`) optimizes for the building computer, and that copy refuses to start on an older CPU.
- Packages built before r25 (`0.1.0.r25.g089a5d2`) may hold an older executable than their version says (the setup
  resumed "compile already done"; fixed). Rebuild with `makepkg -f`.
- The menu's scaling-filter change takes effect at the next start (the filter is built into the present shader).
- After a load the game sometimes picks its own 30 fps mode and stays in it (frames 33 ms apart, ~32 ms of that in
  its own waits, ~1 ms of work): in one of two scripted runs 2026-11-14 for most of the run, in the other for ~260
  frames. The game's own choice (the frame pacer no longer holds it there; fixed 2026-11-14, docs/PROGRESS.md); why
  its frame controller goes there with that much headroom is not yet known.
- Started without a display (seen in containers), the game ends with an abort and a core dump instead of saying
  that it found no display or no Vulkan device.
