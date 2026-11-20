# Known issues

- The port's settings live in the game's own Options menu (docs/IN-GAME-MENU.md). Not yet checked: binding a gamepad
  button on the Controls page (only keyboard binding was tried), the pause menu's Options (whether our rows appear
  there too), and the translations of our rows other than English (drafted, not checked by native speakers). The
  port's version is not on the title screen yet. Key names on the Controls page are SDL's (English).
- Input: gamepad (8BitDo Ultimate 2 Wireless), + / - and the keyboard confirmed by the owner; rumble not yet tested.
- Black around small rooms (castle interiors) is the game's own framing, not a fault.
- Occasional hitches during loads: the 833 ms one was the game's own work loading an area (827 ms of game CPU);
  a few 50-80 ms frames are loads too, two were our render thread (texture work). Not pursued further.
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
- The game is built for x86-64-v2 by default, so a build runs on other x86-64 machines; the installer's CPU level
  question (or `--march v3|native`) optimizes for the building computer, and that copy refuses to start on an older
  CPU.
- The menu's scaling-filter change takes effect at the next start (the filter is built into the present shader).
- After a load the game sometimes picks its own 30 fps mode and stays in it (frames 33 ms apart, ~32 ms of that in
  its own waits, ~1 ms of work): in one of two scripted runs 2026-11-14 for most of the run, in the other for ~260
  frames. The game's own choice (the frame pacer no longer holds it there; fixed 2026-11-14, docs/PROGRESS.md); why
  its frame controller goes there with that much headroom is not yet known.
- Started without a display (seen in containers), the game ends with an abort and a core dump instead of saying
  that it found no display or no Vulkan device.
- The generic AppImage was built and started on the dev machine (Arch-based, rootless podman) only: a start on
  SteamOS / Bazzite / Silverblue, with Docker instead of podman, and on a system without some of the copied
  libraries is unchecked. Rootless podman needs the user's `/etc/subuid` range for the image's apt
  step; whether SteamOS's `deck` user has one is not known. Running the package and the AppImage on one computer
  shares the player folder: each start re-links it to the one started.
