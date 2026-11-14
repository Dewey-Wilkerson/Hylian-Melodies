# Progress

Newest entry last. "Built" = compiled, "boots" = ran to a stated point, "plays" = was played.

## Status at a glance

| Milestone | State |
|---|---|
| M0 Recon | done (docs/RECON.md) |
| M1 Skeleton and guardrails | done: hook rejects keys/NSO/blobs, proven by tests/test_check_content.py |
| M2 Extraction | done: hactool built from pinned commit; check+extract verified, resume after kill tested |
| M3 Lift | done: main+sdk lift (0 unsupported insns) and link with --no-undefined |
| M4 Boot, headless | done: main loop runs headless (menu music, ~30 fps of presents, no crash); every stub documented in docs/services.md |
| M5 Graphics | done: Vulkan renderer; loading screen, both splash videos and the title screen drawn correctly at 61 fps |
| M6 Audio | done by measurement: 10 min, 0 gaps, card clock ~25 ppm from system clock, our latency share ~11-32 ms; not yet checked by ear |
| M7 Input and saves | done: real gamepad verified by the owner, scripted input, saves survive kill -9; keyboard and rumble not yet tried by hand |
| M8 Playable | done: a 7-minute owner session (title, crypt, castle, a dungeon area) at 61 fps with saves and a clean window close; DLC served |
| M9 Packaging | done: `makepkg` builds the package from a clean directory and resumes after interruption; contents and build-path checks pass (docs/packaging.md) |
| M10 Polish | in progress: 60 Hz frame pacing, native-scale sharp scaling, FPS display; settings documented |
| M5-M8, M10 | not started |
| M9 Packaging | launcher + pacman hooks written and tested early; PKGBUILD not yet |

## Log

- 2026-11-12 M0: environment recorded (DEV-ENVIRONMENT.md), five references cloned to `~/refs` and compared
  (REFERENCE-NOTES.md), XCI analysed: Complete-edition style cart with 1.4.0 update + 4 DLC; not Unity (C++ engine,
  nn::gfx/NVN, FMOD over AudioOut); recommendation: build on LASRecomp.
- 2026-11-12 M1: skeleton, MIT license, notices, `.gitignore`, `tools/check_content.py`, `.githooks/pre-commit`,
  CONTRIBUTING, AGENTS/CLAUDE. Tests: 12/12 pass. LAS Recomp's imported tree removed from the working tree
  (still in history at `9c20fa2`).
- 2026-11-12 M2: `tools/build_hactool.py` (SciresM/hactool `1d64a83`, no patches needed on Linux, ~3 s build);
  `installer/` check + extract with JSON events, resume (also after SIGKILL), CNMT and known-good hash verification,
  title keys via a private temp HOME, DLC extracted to `aoc/`. Dev install: `~/.cache/hylian-melodies/dev` (1.8 GiB).
  Tests: 19 unit + 1 game-gated extraction round trip, all pass; no key values in any log (scanned).
- 2026-11-12 M3: `recomp/` = LAS Recomp's lifter (MIT) + own Unicorn-free jump-table interpreter; parallel chunk
  emission. 1.4.0: `main` 20,052 functions / 715 tables, `sdk` 33,586 / 515, 0 unsupported instructions, ~12 s to
  generate. `tools/build_game.py` (Ninja, clang -O1 -march=x86-64-v3) compiles all 57 chunks and links them with
  `--no-undefined` against `tests/c/linkcheck_stub.c`: no unresolved symbols. Full compile ~4 min on 16 threads,
  peak ~6 GB after limiting the all-label fallback (DECISIONS.md). Installer `lift` step wired.
  Also: `packaging/arch/hylian-melodies.sh` and `hylian-melodies-recomp.install` with tests (8 + 3), all pass.

## Next (M4: boot, headless) - original plan, steps 1-2 done 2026-11-13

1. Restore LAS Recomp's core runtime from history (`git show 9c20fa2:runtime/...`): main.c, loader.c, kernel.c,
   ipc.c, dispatch.c, services/{fs,hid_set,audio,time,acc,am,misc}.c, hle/{libc,heaps,bindings,nvn_boot,movie,
   swkbd,vi}.c, platform/linux.c, paths.c, settings.c, crash_explain.c, fnprof.c. Strip Link's Awakening features
   (rando, cosmetics, game_addresses, hooks, UI tabs). Record each file in THIRD_PARTY_NOTICES.md.
2. `tools/build_game.py --target game`: runtime + generated code -> one executable; `rt_jt_miss`.
3. Headless boot mode (`HM_HEADLESS=1`): run nn::init::Start, log every IPC service/command and SVC; reach the
   engine's init. Compare SDK 6.5 IPC layouts with what LAS implements.
4. Service list from RECON.md section 5; stubs documented in docs/services.md.
- 2026-11-13 M4 (partial): LAS Recomp's core runtime restored and adapted (THIRD_PARTY_NOTICES.md), new
  `main.c` (data next to /proc/self/exe, `HM_GAME_DIR`, `HM_HEADLESS`), new RomFS/DLC part of `fs.c` (image laid
  out from `romfs/` by `romfs_build.c`), `rt_jt_miss`, `tools/build_game.py --target game` -> one executable
  (`~/.cache/hylian-melodies/build/hylian-melodies`). **Boots** headless through SDK init, both modules'
  constructors, the game's logger, RomFS mount (679 files), time, vi layer; stops in graphics setup at the first NVN
  buffer map (152 NVN entry points unimplemented). Trace: docs/services.md. Env vars renamed `LARECOMP_*` -> `HM_*`.

## Next

1. Restore LAS Recomp's NVN layer (`git show 9c20fa2:runtime/nvn/...`: objects.c, cmdbuf.c, formats.c, tegra.c,
   astc.c, rqueue.c, maxwell/translate.c, vulkan/*) and `third_party/` pieces it needs (VMA from the system header,
   imgui later), first with a headless backend that only records, so M4 can finish: run until the engine's main
   loop, document every stub in docs/services.md.
2. Check `aoc:u` reports the four DLC; check `movie::`/`glslc` when reached (HLE in hle/movie.c over FFmpeg; glslc
   over glslang/shaderc).
3. Then M5: SDL3 window + Vulkan backend (`ui_headless.c` replaced), shader translation, title screen.
- 2026-11-13 M4 (cont.): NVN front end restored with a headless null backend (0 unimplemented NVN calls);
  `nn::hid` HLE + controller applet; save journaling of new files (bug found by a killed run, fixed, verified by a
  rollback in a later run); `HM_HEADLESS_SECONDS`. **Boots** headless through the engine's whole init (pools,
  textures, audio objects, save file) to the first `movie::` call. Side study on a NecroDancer mod: not worth it.

## Next (updated 2026-11-13)

1. `movie::` HLE: restore LAS Recomp's `runtime/hle/movie.c` (FFmpeg), adapt, add `-lavformat -lavcodec -lavutil
   -lswscale` to `tools/build_game.py`; or stub "no video" first to see what follows.
2. Continue the headless boot until the main loop runs (presents through the null backend); document every stub in
   docs/services.md; then M4 is done.
3. M5: Vulkan backend (`runtime/nvn/vulkan/`), SDL3 window replacing `runtime/ui_headless.c`, Maxwell translator.
- 2026-11-13 M4 **done**: movie HLE (LAS Recomp's, over FFmpeg) with this game's end-of-stream status `0x2000`
  (found by reading how the game checks the result); offline `nifm`/`bsd` (`services/net.c`). Headless: both
  splash videos play to the end, the network is found offline, the main-menu music plays, the main loop presents
  904 frames in 30 s with no crash and no unimplemented call. Acceptance: docs/services.md lists every service and
  each stub. Not yet checked: the DLC listing (`aoc:u`).

## Next (M5: graphics)

1. Restore LAS Recomp's Vulkan backend (`git show 9c20fa2:runtime/nvn/vulkan/...`: device, exec, record, shaders,
   textures, vma) and the Maxwell translator (`runtime/nvn/maxwell/`), shaderc (`pkg-config shaderc`), the system
   VMA header; build it instead of `nvn/null_backend.c` when not headless.
2. SDL3 window + present loop replacing `runtime/ui_headless.c` (LAS Recomp's ui_run without its menus).
3. First frame, then the title screen; frame dumps for comparison (kept outside the repo).
- 2026-11-13 M5 **done**: LAS Recomp's Vulkan backend, Maxwell translator and SDL3 window restored and adapted
  (`tools/build_game.py --target game`). Fixes along the way: TLD4 (texture gather) in the translator; the present's
  crop (the stand-in left it unset: one texel stretched over the window); the movie decoder writing into the game's
  own buffer (green videos); the "format changed" event (a 5 s stall at the second video). Verified with window
  captures (`HM_WINDOW_SHOT`, kept outside the repo): loading screen, both splash videos, and the title screen
  matching the console's, at a steady 61 fps on the RX 7600 XT with no translation failure and no skipped draw.
  Not yet: input (M7), integer pixel scaling (M10).

## Next (M6: audio)

1. Listen: FMOD -> `audout` -> SDL3 (the menu music already plays). Record the output with `HM_AUDIO_WAV`-style
   capture if LAS Recomp's audio code has it (`a->wav`), check pitch, gaps and drift over 10 minutes.
2. Make `audout` pacing console-like (buffer release at 48 kHz, low and stable latency), add the latency setting
   (`audio_latency_ms`), measure and document it in docs/audio.md.
- 2026-11-13 M6: audio stats (`HM_AUDIO_STATS`) and per-output PCM capture (`HM_AUDOUT_WAV`); device period and
  queue made settings (`audio_period` 256, `audio_queue_ms` one period); default settings file
  `packaging/hylian-melodies.ini`. 10-minute menu run: 0 gaps, release rate 47,998.6-47,999.6 frames/s each
  minute (~-25 ppm against the system clock), constant 26.7 ms in our stream, 61 fps; capture clean. Details and
  latency budget: docs/audio.md. Needs the owner's ears for the final word.

## Next (M7: input and saves)

1. SDL3 gamepad + keyboard into `runtime/hle/input.c` (`g_input_buttons`, `g_input_sticks`), polled at the start of
   each game frame (the game reads `GetNpadState` once per frame); rumble through SDL; rebinding in the ini.
2. Saves: the journal is in place (`services/fs.c`); test a save/load round trip that survives `kill -9`.
- 2026-11-13 M7: `runtime/ui/input.c`: SDL3 gamepad (by position, as on the Switch) and keyboard, event-driven
  state read at the game's poll (no queue), ini rebinding (`key.<button>`, `pad.<button>`), `gamecontrollerdb.txt`,
  rumble from the game's vibration values, scripted input (`HM_INPUT_SCRIPT`). Scripted presses drive the menus
  (save slots, mode select, the game's own latency calibration) into play: Cadence in the opening clearing, HUD
  drawn. Saves: the game wrote and committed its save; killed with SIGKILL mid-play; on restart the title offered
  Continue with the file's date and it loaded back into play. `tests/test_saves_kill9.py` (game-gated, ~80 s)
  repeats it and passes. Not verified: a physical gamepad (none connected) and real key presses (the agent can't
  press keys); rumble.

## Next (M8: playable)

1. The owner plays: keyboard and a gamepad, a full session from the title to the first dungeon and a clean exit
   (closing the window). The agent can't judge feel; it can run long scripted sessions and watch the logs.
2. Fix what that finds; log the rest in docs/KNOWN-ISSUES.md.
3. Known first candidates: the dynamic-resolution glitch (the image drawn shrunk into the window's corner at
   moments), pixel-perfect scaling, the overlay menu.
- 2026-11-13 M7 (cont.): the owner connected an 8BitDo Ultimate 2 Wireless and played two minutes: recognised by
  SDL, every button tried reached the game (`HM_LOG_INPUT=1` logs held buttons), 12 saves committed in play.
- 2026-11-13 M8 (started): the owner played. Fixed: a crash ("no function at ...") from a jump table the lifter
  missed (FP registers d8/d9 mistaken for x8; bounds-check search widened to 32 instructions): main 716 / sdk 516
  tables. Debug dump key: P with `HM_DEBUG_KEYS=1` (the desktop takes F9). Open: wrong colours and flickering lines
  **underground only**. Diagnosis so far: every sprite uses one shader whose per-draw tint comes from constant
  buffer 3; underground tints vary per tile. Suspect LAS Recomp's "GPU overlap" (the game writes the next frame's
  data while the GPU still reads this one). Test running: `HM_GPU_OVERLAP=0`; if the owner confirms it fixes the
  colours, make overlap off the default (or fix its uniform snapshot) and re-test. Also open: image drawn shrunk
  into the window's corner at times (dynamic resolution).
- 2026-11-13 M8 (cont.): underground colours fixed (3D LUT layout: block of at most 16 GOBs); flickering lines and
  soft text fixed by rendering at native scale (default now) and a sharp-bilinear present. Both confirmed by the
  owner. GPU overlap was ruled out as a cause (stays on).
- 2026-11-13 M8 **done**: the owner played ~7 minutes from the title through the crypt and castle into a dungeon
  area: 61 fps, 38 save commits, no crash, closed with the window's close button ("window closed", exit 0).
  Captures reviewed: colours right everywhere; black around small rooms is the game's own framing. DLC: `aoc:u`
  now lists the four packs from `aoc/` (LAS Recomp's said "none", with its own game's base ID); the game mounts
  all four and Select Mode offers more than Story Mode. Hitches seen: one 833 ms frame at an early load, a few
  50-80 ms; to look at in M10.

## Next (M9: packaging)

1. `packaging/arch/PKGBUILD` per brief section 8 (prepare/build/package, `_firmware()`, events.py heredoc, pkgver).
2. Installer stages still missing: compile (tools/build_game.py --target game into the stage), shaders (first run
   compiles them today; decide whether a prepare step is worth it), cleanup.
3. `makepkg` from a clean directory, resume after interruption, `pacman -Qlp` checks, build-path grep (brief 8.5).
- 2026-11-13 M9 **done**: `packaging/arch/PKGBUILD` (owner's decisions: /opt/hylian-melodies, XDG user data, XCI
  only, no firmware, no shader step), installer compile + cleanup steps, the game's own icon from the dump for the
  menu entry, `--fullscreen` / `--windowed`, build paths mapped out of the executable. Checks (brief 8.5): clean
  `makepkg -Cf` in ~2 min; interrupted mid-compile then `makepkg -f` resumed (extract and lift skipped) and
  finished; `pacman -Qlp`: game under /opt/hylian-melodies, no settings/profile/logs/cache/setup record inside it,
  launcher, icon, desktop entry, licence, support files; no file names the build directory; launcher and
  pre_remove tests pass. Building is done; installing is the owner's.

## Pin (2026-11-13)

Last known good before M10: git tag `pin-m9-package-ok` (M0-M9 done, package passes its checks, game playable), and
its package in `~/.cache/hylian-melodies/pin-m9/`. Revert: `git checkout pin-m9-package-ok` (or
`git reset --hard pin-m9-package-ok` on a branch, after confirming with the owner), then rebuild with makepkg.
- 2026-11-13 M10 (started, after the pin): the game ran at 61.07 fps because nothing paced it (it never waits on
  the vsync event; presents returned at once); presents now keep the Switch display's 60 Hz cadence: 60.0 fps,
  frame times at most 17-18 ms. FPS in the window title (`show_fps`). Load hitches traced to the game's own loading.
