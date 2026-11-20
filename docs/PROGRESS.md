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
| M10 Polish | in progress: 60 Hz frame pacing, native-scale sharp scaling, FPS display, overlay settings menu in the game's own fonts |
| Installer | in progress: system packages (pacman / `.deb` / `.rpm`) through `python3 -m installer.tui`; see the last hand-off |

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

Last known good before M10: git tag `base-functionality` (named `pin-m9-package-ok` until 2026-11-14) (M0-M9 done, package passes its checks, game playable), and
its package in `~/.cache/hylian-melodies/pin-m9/`. Revert: `git checkout base-functionality` (or
`git reset --hard base-functionality` on a branch, after confirming with the owner), then rebuild with makepkg.
- 2026-11-13 M10 (started, after the pin): the game ran at 61.07 fps because nothing paced it (it never waits on
  the vsync event; presents returned at once); presents now keep the Switch display's 60 Hz cadence: 60.0 fps,
  frame times at most 17-18 ms. FPS in the window title (`show_fps`). Load hitches traced to the game's own loading.

## Next (M10: overlay menu) - handoff, 2026-11-13

Done so far in M10: 60 Hz pacing, FPS in the title, F11 / Alt+Enter fullscreen toggle (88e946b), and
`tools/fetch_imgui.py` (ImGui v1.91.9 at `97428e8` into git-ignored `toolchain/src/imgui`, plus
`tools/imgui/0001-dynamic-vertex-input.patch`, LAS Recomp's AMD fix renamed to `hm_imgui_dyn_vertex`). Plan:

1. **Glue**: restore LAS's `runtime/nvn/vulkan/imgui_glue.cpp` (`git show 9c20fa2:runtime/nvn/vulkan/imgui_glue.cpp`,
   86 lines, MIT) as `runtime/ui/imgui_glue.cpp`: `vk_imgui_backend_init()` (dynamic rendering, `g_vk.*`,
   `rec_drain()`, fonts texture), `_shutdown()`; set `hm_imgui_dyn_vertex = g_vk.vids`. Rename LAS strings at once.
2. **Build**: `tools/build_game.py` (game target only, not headless) calls `tools/fetch_imgui.py`, compiles
   `imgui.cpp imgui_draw.cpp imgui_tables.cpp imgui_widgets.cpp backends/imgui_impl_{vulkan,sdl3}.cpp` with the
   existing `rtcxx` rule (`-I<imgui> -I<imgui>/backends`, `-DIMGUI_IMPL_VULKAN_NO_PROTOTYPES` only if the glue loads
   functions itself; check how the device is created); `--imgui DIR` override; the stamp keeps rebuilds offline.
3. **Menu** `runtime/ui/menu.cpp` replacing `menu_stub.c` (keep `menu.h`'s six functions; device.c already calls
   `menu_render` inside `vk_overlay_begin/end`, `menu_handle_event` per SDL event, `menu_apply_window_requests`
   per frame; `HM_MENU_AT=<frame>` opens it for screenshot tests via `menu_test_open`). References, MIT, all in
   `9c20fa2`: `runtime/ui/menu.mm` (1079 lines, plain C++), `option_rows.mm/.h`, `controls_ui.mm`, `pad_nav.mm/.h`.
   Take only the shape; nothing Link's Awakening. Open/close: Esc or F1, pad Minus+Plus held together (`input.c`
   must not pass those to the game while the menu is open: `menu_input_captured()`). Tabs: Video (fullscreen,
   upscale filter 0/1/2, show FPS, frame pacing), Audio (volume), Controls (rebind keyboard and pad per Switch
   button, reset to defaults), About (version `hm_version()`, folder paths). Changes apply live where the runtime
   allows (filter, FPS, pacing, volume, fullscreen); say "next start" for the rest.
4. **settings_save()** in `runtime/settings.c`: rewrite `hylian-melodies.ini` in place, keep comments, unknown keys
   and `key.`/`pad.` lines not touched by the menu; write to `.tmp` then rename. The file lives in the player's
   folder (launcher seeds it); a test in `tests/` with a C harness like LAS's `tools/test_settings.c` or via a
   small python reimplementation check.
5. **Package**: PKGBUILD `prepare()` runs `python tools/fetch_imgui.py --src "$srcdir/toolchain/src/imgui"` (build
   stays offline) and passes `--imgui` through the installer's compile step (installer/steps.py -> build_game.py);
   `makepkg -f` in packaging/arch, then `git checkout -- PKGBUILD` (pkgver rewrite). Tests: `test_pkgbuild` grep.
6. **Check and document**: run with `HM_MENU_AT=600 HM_WINDOW_SHOT=650`, look at the capture; docs/controls.md
   (menu keys), docs/packaging.md, DECISIONS line, this file; commit. Owner checks still open: rumble, `show_fps`.
- 2026-11-14 M10: overlay settings menu (`runtime/ui/menu.cpp`, Dear ImGui on the Vulkan backend): F1 or Minus+Plus;
  Video, Audio, Controls (keyboard and gamepad rebinding), About; the game gets no input while it is open.
  `settings_save()` writes changed keys back into the player's ini in place (tests/test_settings_save.py). The menu
  draws with the game's own large serif display face read from the RomFS at start (`runtime/ui/game_font.c`, our
  reader: BC4 block-linear sheets; 42 px line, scaled to the window, heading 1.5x; owner's choice). Captures (kept outside the repo)
  checked at 1856x1044: crisp text, all bindings listed. Also: the setup now redoes lift/compile when their sources
  changed (makepkg -f had packaged a stale executable: packages before r25 lack the M10 commits); the ini takes
  south/east/west/north for face buttons (SDL3 doesn't); frame pacing follows the setting live.
  Not verified by hand: closing, saving and rebinding with real presses (the agent can't press keys); rumble.

## Next (M10, after the menu)

1. Owner: open the menu (F1), change a setting and a binding, close it, check `hylian-melodies.ini` and the effect.
2. Optional: a dialog-box texture from the game for the menu panel (needs finding which texture; facts only in docs).
3. Remaining M10 items from the brief; keep `docs/KNOWN-ISSUES.md` current.

## Next (publication and installer) - handoff, 2026-11-14

Owner's decisions from the 2026-11-14 planning talk (information gathering only; nothing below is done):

1. **Leak scan result.** The tracked tree passes `tools/check_content.py --tracked`; no personal data in files. Blockers
   are in git history only: commit `9c20fa2` (the LAS Recomp import) holds Link's Awakening data
   (`runtime/game_addresses/`, `runtime/nvn/shader_variants.txt`, `third_party/LAS-Randomizer`, `tools/rando`) plus
   vendored fonts/ImGui; every commit's author is the owner's personal email. Minor, owner's call: 82 mangled SDK
   symbol names in 8 runtime files (e.g. `nn::init::Start` in `runtime/main.c`), ~10 comments naming game code
   addresses (e.g. `runtime/hle/movie.c`).
2. **History cleanup (first; needs the owner's go-ahead for the rewrite).** New history without `9c20fa2` and with a
   noreply/pseudonymous author (squash into one first commit, or `git filter-repo`). Commit IDs change; the tag
   `pin-m9-package-ok` must be re-pointed (owner's say-so) and the old history kept locally as a backup branch/bundle.
3. **Private git repo** for testing (push only with the owner's explicit OK at that time); public later by flipping one
   default URL.
4. **Generic builds by default.** `tools/build_game.py` default -march becomes x86-64-v2 (today: v3 when the CPU has
   it); `--march v3|native` is the opt-in "optimize for this computer's CPU". First measure v2 vs v3 frame times
   (test runs need the owner's OK). The machine-id binding idea was dropped.
5. **Installer design doc** (`docs/installer.md`, before code): `curl | sh` POSIX bootstrap (prompts via /dev/tty,
   pinned tag + checksum, `--source` override for a local checkout or the private repo) -> Python stdlib-curses TUI:
   desktop file picker through the portal (zenity/kdialog fallback, in-terminal browser over SSH), XCI and keys read
   in place (already so: `installer/hactool.py` passes `-k <path>`), early `check`; outputs: system package
   (pacman/.deb/.rpm), loose directory (user data stays in it), AppImage (portable variant: v2 + `zig cc` old-glibc
   target + bundled SDL3/ffmpeg/shaderc), Flatpak last; build options (CPU level, keep build cache); launch options
   for the .desktop (fullscreen, env vars) with explanations; a manifest so rerunning offers update / change options
   / uninstall. Never upload, never sudo from the script.
6. **Env var audit** for the TUI: 192 `getenv("HM_...")` in `runtime/`; sort into player / troubleshooting / dev,
   remove dead LAS leftovers, one documented list checked against the code by a test.
- 2026-11-14 publication, started: step 1 (history) prepared, not applied: backup bundle of the full old history in
  `~/.local/share/hylian-melodies/history-backup/hylian-melodies-pre-rewrite-74231d6.bundle` (verified); a
  plumbing rewrite (same trees, messages, dates; new parents and identity; drops the root import commit) dry-runs
  clean: 28 commits, same final tree, the import unreachable, no personal e-mail left. Waiting on the owner for the
  author identity, the go-ahead and the tag. Step 4 (generic builds) done in code: x86-64-v2 default, `--march
  v3|native` opt-in through build_game.py, the setup and the PKGBUILD (`HM_MARCH`); v2 vs v3 frame times not yet
  measured (owner's OK for the run). Step 5: `docs/installer.md` part 1 holds the bootstrap + TUI design.
- 2026-11-14 history rewritten (owner's OK; author pseudonym "Bagu" <bagu@hylian-melodies.invalid>, also the repo's
  local git identity): the LAS Recomp import commit is gone, every commit ID changed, so commit IDs quoted above
  (and `git show 9c20fa2:...` in old plans) refer to the old history: read LAS code from `~/refs` instead. Old
  history: `~/.local/share/hylian-melodies/history-backup/hylian-melodies-pre-rewrite-0b2ec32.bundle`. Tag
  `pin-m9-package-ok` was then re-pointed to the rewritten twin `2d68a8a` and renamed `base-functionality` (owner's
  OK; same message). Old objects stay in `.git` until reflog expire + gc (owner's call).
- 2026-11-14 v2 vs v3 measured (owner's OK): both built from the same generated C (34-35 s each), four 90 s scripted
  runs alternating v2/v3 (title menus into play, then steps left/right), fresh profile in a separate game folder,
  `HM_LOG_PACE=1`. The game's work per frame (pacer's cost): median 1.06 / 1.09 ms (v2), 1.10 / 1.12 ms (v3); the
  pacer's own "a frame at 60" averages 1.0-1.4 ms either way. No measurable difference; run-to-run noise is larger.
  Found on the way (both levels alike): the pacer held the game's 30 fps mode in all four runs, in two of them for
  most of the run, although frames take ~1 ms: docs/KNOWN-ISSUES.md.

## Next - handoff for a fresh session, 2026-11-14

State: publication steps 1, 2, 4 and 5 of the section above are done (history rewritten as "Bagu"; revert tag
`base-functionality`; x86-64-v2 default, v3/native opt-in, measured equal; installer design in `docs/installer.md`
part 1). Nothing has been pushed yet: there's no remote. A side session is fixing the pacer's false 30 fps hold
(docs/KNOWN-ISSUES.md); check `git log` and this file for its result before starting.

Open, in order (each needs the owner where marked):
1. Owner's call: `git reflog expire --expire=now --all && git gc --prune=now` to drop the old history's objects
   (backup bundles in `~/.local/share/hylian-melodies/history-backup/`).
2. Env-var audit (publication step 6): sort the `getenv("HM_...")` in `runtime/` into player / troubleshooting /
   developer, remove dead LAS leftovers, and turn the result into `installer/options.py` plus a test that checks it
   against the code (docs/installer.md sections 5 and 7).
3. Own LZ4 block decoder replacing `python-lz4` in `recomp/nso.py`; `installer/deps.py` (docs/installer.md, section 8).
4. TUI model + `--answers` + plain prompts, then curses screens and file picker; loose-folder output; manifest.
5. Bootstrap `install.sh` + `tools/release.py`; private repo (owner creates it; push only with their OK then).
Open questions 5 (AppImage tools) and minor leak items (mangled SDK names, code-address comments) are the owner's.
- 2026-11-14 frame pacer fixed (owner's OK for the runs): it held the game's 30 fps mode with ~1 ms frames for three
  reasons. (1) The display cadence's wait (objects.c `display_cadence`) wasn't counted as idle, so every frame at 60
  read ~16.4 ms busy; now it adds to `g_blocked_ns`. (2) A frame shown late counted as not fitting 60 even when the
  game itself had waited out the second vsync (its own 30 fps mode: 32 ms blocked, 1 ms work, 0.3 ms GPU); now a late
  frame counts only when its work plus its GPU and present waits take more than its vsyncs (and late is measured
  against the present interval asked for). (3) Movie frames are presented from another thread, so the per-thread
  counters wrapped (cpu / blocked ~1.8e16 ms); a frame from another thread now starts the counts over. Unit tests:
  `tests/test_pace.py` (pace.c on a simulated clock, 7 cases; the old pace.c fails the three regression cases).
  Same scripted run, fresh profile (logs `~/.cache/hylian-melodies/bench-pacefix3-run{1,2}.log`): no hold in either
  run (before: 2-8 holds a run, "backing off"), busy median 0.75 / 1.54 ms, no wrapped values. The game's own 30 fps
  mode after loads remains (docs/KNOWN-ISSUES.md).
- 2026-11-14 installer design pass on system packages (owner: the first version gets those right). Every build and
  run-time need read from the code and checked against the Debian, Ubuntu, Fedora and Arch package databases:
  docs/installer.md section 9 (supported from Debian 13, Ubuntu 26.04, Fedora 43; openSUSE unchecked). Resolved in
  the design: one staged tree and three packers instead of calling the developer PKGBUILD (a tarball has no `.git`);
  run-time dependencies derived from the executable; order of work with packages first (section 8). Found: the VMA
  package is AUR only (KNOWN-ISSUES), Fedora's FFmpeg may not decode the movies, nothing compiled outside Arch yet
  (OPEN-QUESTIONS 7-9). Small fixes: build_game.py stops on a failing pkg-config; Vulkan application name
  "LARecomp" -> "Hylian Melodies"; README status. Publication audit: content guard and tests pass, one author
  identity, no personal strings in files or history; still open: gc of the old history's objects (826 unreachable),
  the PKGBUILD's placeholder `url`, `license=(MIT)` on a package that holds the game, whether the brief
  (`hylian-melodies-prompt.md`) is published. Not committed yet.
- 2026-11-14 VMA pinned (owner's OK): `tools/fetch_vma.py` (v3.5.0), `--vma` through build_game.py, the setup and
  the PKGBUILD; `vulkan-memory-allocator` dropped from makedepends. The game target builds and links here with the
  fetched header (and with the pkg-config check and the renamed Vulkan application name); not run, no makepkg run.
- 2026-11-14 package lists tried in containers (owner's OK; podman, bare images of Debian 13, Ubuntu 26.04, Fedora
  43 and 45, openSUSE Tumbleweed): the install command of docs/installer.md section 9, then hactool and the game
  built from the dev machine's generated C (mounted read-only), unit tests, `DT_NEEDED` traced to packages. All five
  build and link. Fixed on the way: Debian 13's SDL 3.2 lacks `SDL_SavePNG` (screenshots fall back to `.bmp`).
  openSUSE's names added to the table. Images, build outputs and logs removed afterwards (owner). The game was not
  run in the containers (no display); movies through `libopenh264` on Fedora/openSUSE are untested.
  Next: `installer/deps.py` from that table + test, then the three packers (section 8).
- 2026-11-14 installer step 1 (docs/installer.md section 8): `installer/deps.py` (`python3 -m installer.deps`:
  capability checks, distro family from os-release, the one install command, a note for releases without SDL3) with
  `tests/test_deps.py`; own LZ4 block decoder `recomp/lz4block.py` (byte-identical to python-lz4 on all 15 segments
  of the five modules; `tests/test_lz4block.py`), `python-lz4` dropped from the PKGBUILD and the docs. The lift was
  not rerun end to end; makepkg not rerun. Next: the three packers on the staged tree (section 8, step 2).
- 2026-11-14 old releases (owner: find a workaround for no SDL3 on Debian 12 / Ubuntu 24.04). `tools/build_sdl3.py`
  (pinned release-3.4.20, static, CMake) + `build_game.py --sdl3` + `--sdl3` through the setup; `installer/deps.py`
  switches to the "own SDL3" needs on such a release, checks clang >= 17, takes `convert` for ImageMagick 6, and
  marks Debian 12 unsupported. Container results (bare images, generated C from the dev machine): Ubuntu 24.04
  builds and links with the static SDL3 (not run). Debian 12: needed clang-19 (in its repos; clang 14 lacks
  `__builtin_elementwise_fma`), a guard for Vulkan 1.3.239 headers (exec.c, done), then failed at link on its broken
  `libshaderc1`: unsupported until shaderc is built from source (the AppImage's job). docs/installer.md section 9.
  Not done: running a game linked with the static SDL3 (needs the owner's OK; buildable here with
  `tools/build_sdl3.py` then `build_game.py --sdl3 toolchain/sdl3`).
- 2026-11-14 Debian 12 supported (owner's call). `tools/build_shaderc.py` (shaderc v2026.4 + the glslang,
  SPIRV-Tools, SPIRV-Headers revisions of its DEPS file; one static `libshaderc_combined.a`; 23 s here),
  `build_game.py --shaderc`, `--shaderc` through the setup; `installer/deps.py`: `shaderc: own` on Debian 12,
  `clang-19 lld-19` named there, `use_newer_clang()` (also called by `python -m installer`). build_game.py no longer
  asks pkg-config about our own SDL3 folder (a space in the path broke the flags). End-to-end container run with
  deps.py choosing the packages: Debian 12, Ubuntu 24.04 and Debian 13 all install, build and link; 78 unit tests
  pass in each. Built here too with both own libraries: `~/.cache/hylian-melodies/build-own/hylian-melodies` (from
  `toolchain/sdl3`, `toolchain/shaderc`). Run for 20 s (owner's OK; `bench-game` folder, `HM_VK_NO_SPIRV_CACHE=1`
  so shaderc compiles): window, audio out, shader programs compiled, both splash movies (H.264, AAC) decoded, title
  screen captured at frame 800 as PNG, 824 frames, clean exit, no error lines. Not checked by a person at the
  screen or by ear. Next: the three packers (docs/installer.md section 8, step 2).
- 2026-11-14 packers (docs/installer.md section 8, step 2): `installer/pack.py` (`python3 -m installer.pack`): one
  package tree from a finished setup folder, then makepkg / dpkg-deb / rpmbuild; dependencies derived from the
  executable; hooks shared with the Arch `.install` file; `tests/test_pack.py`. Arch package built here from
  `packaging/arch/src/stage` (35 s; file list identical to r28's; not installed). `.deb` and `.rpm` built,
  installed with the printed command, launcher run as another user, removed, in containers of Debian 13, Ubuntu
  24.04, Fedora 45, openSUSE Tumbleweed: all clean, saves kept on removal. Seen there: without a display the game
  ends with an abort (core dump) rather than a message: worth a clear error (docs/KNOWN-ISSUES.md). Test images,
  outputs and packages removed. Next: step 3 (UI model, `--answers`, plain prompts; the flow that runs deps ->
  own libraries -> setup -> pack; manifest), then the options registry, the bootstrap.
- 2026-11-14 installer flow (section 8, step 3; docs/installer.md section 10): `installer/plan.py` (plan, checks,
  manifest), `installer/flow.py` (deps -> hactool / own SDL3 / own shaderc -> input check -> setup -> pack ->
  manifest), `installer/tui.py` (`python3 -m installer.tui`: plain prompts, or `--answers FILE`), `tests/test_tui.py`
  (scripted console, fake flow). Unattended run here with the real dump and `XDG_CACHE_HOME` / `XDG_DATA_HOME` in a
  scratch folder: 2 min 50 s to a pacman package (file list equal to r28's), manifest written, no key value in the
  logs. The prompts themselves were only driven by tests, not typed by a person. Owner: immutable systems
  (SteamOS) will get the AppImage as their channel; constraints written down in section 10. Next: options registry
  + env-var audit and `launch.env` (step 4), bootstrap `install.sh` + `tools/release.py` (step 5), curses screens
  and file picker (step 6), then AppImage.

## Next - handoff for a fresh session, 2026-11-14 (evening)

State: the first release is the **system package** (pacman / `.deb` / `.rpm`), and its whole path exists and is
committed (`14a0138`; clean tree; nothing pushed, no remote yet). `python3 -m installer.tui` (plain prompts or
`--answers FILE`) runs: `deps.py` (what the system lacks, the one command) -> hactool, plus our own static SDL3 /
shaderc where a release needs them -> early input check -> setup -> `pack.py` -> manifest. Supported and tried in
containers: Arch, Debian 12 and 13, Ubuntu 24.04 and 26.04, Fedora 43/45, openSUSE Tumbleweed
(docs/installer.md sections 4, 9, 10; the design's order of work is section 8). 99 unit tests.

Open, in order (docs/installer.md section 8, steps 4 to 6):
1. **Options registry + env-var audit** (`installer/options.py`): sort the `getenv("HM_...")` in `runtime/` into
   player / troubleshooting / developer, remove dead LAS leftovers, a test that checks the registry against the
   code; `launch.env` read by the launcher (`packaging/arch/hylian-melodies.sh`: parsed, never sourced, `HM_*`
   only); launch options in the prompts and the manifest (section 5).
2. **Bootstrap** `install.sh` (POSIX sh, section 1) + `tools/release.py` (fills tag and tarball SHA-256). Test with
   `--source PATH` first; the private repository is the owner's to create, and any push needs their OK then.
   The bootstrap needs python3 on a bare system (Debian/Ubuntu images have none): its check must say so.
3. **Curses screens + file picker** (sections 2, 3) on top of `plan.py` / `flow.py`; disk space on the summary.
4. **AppImage channel** for immutable systems (SteamOS), owner's direction: section 10. `plan.OUTPUTS` /
   `PLANNED` already name it. Still to bundle: FFmpeg. Build place: another computer, or a container on the device.
5. Smaller: a clear message instead of an abort when there is no display (KNOWN-ISSUES); `-j` for the compile is
   not plumbed through the setup; `packaging/arch/PKGBUILD` was changed (VMA fetch, no python-lz4) but `makepkg`
   was not rerun with it; the flow's removal of `work/pack` after packing was added after the last full run.

Owner-side, unchanged: `git reflog expire --expire=now --all && git gc --prune=now` for the old history's objects;
the PKGBUILD's placeholder `url`; whether the brief (`hylian-melodies-prompt.md`) is published; movies through
`libopenh264` on Fedora / openSUSE and any package install on a real desktop of another distro are untested
(OPEN-QUESTIONS 8).

How the checks of this session were done (to repeat them):
- **Containers** (owner OK'd pulling images with podman for test builds; remove images and outputs afterwards):
  bare image, install python3, then let `installer/deps.py` print the command and run exactly that, build with the
  repo mounted read-only at `/repo`, `~/.cache/hylian-melodies/gen` at `/gen` (generated C from the dev machine, so
  no dump or keys enter a container), an output folder under `~/.cache/hylian-melodies/ctr/`. For packages: a stage
  made of symlinks to `packaging/arch/src/stage/hylian-melodies/{romfs,exefs,aoc,icon.jpg}` plus the executable
  built there, then `python3 -m installer.pack`, install with the printed command, run the launcher as another
  user, remove. The game cannot start there (no display).
- **Full run here without touching the owner's settings**: `XDG_CACHE_HOME=<scratch>/cache
  XDG_DATA_HOME=<scratch>/data python3 -m installer.tui --answers <file with base and keys>` (about 3 minutes).
- **Static SDL3 / shaderc on the dev machine**: `python3 tools/build_sdl3.py`, `python3 tools/build_shaderc.py`,
  then `build_game.py ... --out ~/.cache/hylian-melodies/build-own --sdl3 toolchain/sdl3 --shaderc
  toolchain/shaderc` (that build exists; it ran 20 s cleanly with `HM_GAME_DIR=~/.cache/hylian-melodies/bench-game
  HM_VK_NO_SPIRV_CACHE=1`). Running the game always needs the owner's OK first.
- 2026-11-14 (late) clean-up before the options registry (owner: check for dead code, LAS-specific code and LAS
  names first). Method: the runtime compiled with one section per function and linked with `--gc-sections
  --print-gc-sections -z nostart-stop-gc` (lists what nothing reaches; a function listed there may still be used
  inlined, so each removal was confirmed by a normal link), `-Wunused`, and greps. Removed, about 2,500 lines, all of
  it code that could not run or always answered "nothing": `runtime/nvn/las_feature_stubs.c` and every call into it
  (recolouring, texture patches, widescreen, mirror mode, pots, hint sheet, warp / save-editor / reboot hooks), with
  `recolour.h` and `texpatch.h`; the in-place reboot (`RT_ON_RESET`, `g_rt_unwind`, the `*_reset` functions); SMAA
  (no shader source was ever here); the `audren:u` mixer and reverb in `services/audio.c` (this game only opens
  `audout:u`; it was a port of Ryujinx code with no notices row); `hle/libc.c` (never wired: the lifter has no
  symbol list); the start screen's process helpers and the never-armed data watchpoint; crash-dialog cases keyed to LAS's messages and its file count; settings nothing read
  (`aspect_unlocked`, `movie_audio`, `audio_latency_ms`, and the fields behind them; the first two were in the
  default ini). Renamed: `LASRECOMP_LOG_APPEND` -> `HM_LOG_APPEND`; the profile nickname "Link" -> "Player"; the
  crash dialog no longer says "GitHub issue" or "makepkg". A Link's Awakening level name in `textures.c` is gone.
  Environment variables read in `runtime/`: 198 -> 175. Python: four unused helpers. Both targets build and link, 99
  unit tests pass. Owner: keep the Windows and macOS branches as stubs (those ports come back later), so the
  `_WIN32` / `__APPLE__` / `__OBJC__` branches removed at first were merged back (docs/DECISIONS.md). Run after
  the clean-up (owner's OK, `bench-game` folder, fresh profile): `tests/test_saves_kill9.py` passes (new game into
  play, saves committed, killed, reloaded); a 50 s run and two 95 s scripted runs end cleanly with no error line,
  0 audio gaps; against the build from before the clean-up with the same script, the capture at frame 2500 is
  identical and the one at frame 3300 (in play) differs in 0.5% of its pixels, spread over the frame (taken to be
  the animated tiles' phase; not looked into further). Shader text is unchanged, so the shader cache stays valid. Left for later, each needs a run (docs/KNOWN-ISSUES.md): the per-draw tint and mirror
  flip in translated shaders, the present shader's colour filter, dynamic resolution /
  FSR, the ambient-occlusion and shadow special cases, stale comments pointing at LAS Recomp's files.
  Next: the options registry (hand-off above, item 1). Owner's cut of the launch options: players get fullscreen /
  windowed and the graphics card; no "no audio" option (a rhythm game); a short troubleshooting list; the rest
  developer-only.
- 2026-11-15 options registry and game settings (hand-off item 1). `installer/options.py` sorts every `HM_*`
  variable `runtime/` reads (`getenv` and the `ENV` macro of `runtime/hle.h`, which the first version of the test
  missed: four variables) into player / troubleshooting / developer / internal; `docs/env-vars.md` is generated
  from it and a test checks both ways. Owner's call after comparing the two: the installer's questions (fullscreen,
  the graphics card when there are several, five troubleshooting settings) are written into the player's own
  `hylian-melodies.ini`, not a `launch.env` turned into arguments and variables by the launcher, which pinned
  fullscreen and frame pacing so a change in the in-game menu was undone at the next start (docs/DECISIONS.md).
  New ini keys read by `runtime/settings.c`: `gpu`, `shader_cache`, `vk_validation`, `log_input`, `audio_stats`
  (each `HM_*` variable still wins); the default ini lists them. The installer edits only its keys and keeps every
  other line; "change the game settings" for an existing install needs no rebuild. The launcher reads no file of
  the player's. Both targets build, 109 unit tests; `settings.c` checked alone against sample files. Not yet run in
  the game (needs the owner's OK): `gpu = N` picking that card and `log_input = 1` logging, from the ini.
  Next: the bootstrap (`install.sh` + `tools/release.py`, item 2 of the evening hand-off).
- 2026-11-15 bootstrap (hand-off item 2). `install.sh`: POSIX sh, one `main` called on the last line (a cut-short
  pipe runs nothing: checked at three cut points and under dash), questions on `/dev/tty` (none there: a message
  pointing to `--answers`), checks Linux x86-64 and python3 >= 3.11 first and prints the distro's install command for
  what is missing (a bare Debian/Ubuntu image has no python3), then a pinned release tarball checked by SHA-256
  into `~/.cache/hylian-melodies/src/<tag>/` (reused offline), or `--source PATH` / `--source URL --ref REF`
  (git, the player's own credentials), and starts `installer.tui --root <src> --source-note ...`, which shows the
  source first. `tools/release.py --repo-url ...` makes the reproducible tarball (content guard over every file;
  the brief left out), the filled `install.sh` and `SHA256SUMS` under `~/.cache/hylian-melodies/release/<tag>/`;
  it pushes and uploads nothing. Release asset instead of GitHub's generated archive (docs/DECISIONS.md).
  `tests/test_bootstrap.py` (8 tests) runs both end to end on a stand-in repository with `file://` releases; the
  real tree's tarball passes the guard. In the local ubuntu:22.04 image, offline (dash): help, missing python3,
  Python too old, no terminal, a cut-short pipe, `--source`. 117 unit tests.
  Not done, needs the owner: a private repository to push to (and the OK to push), then `release.py` against a real
  tag and `curl | sh` from it. No tag was created.
  Next (evening hand-off items 3 to 5): curses screens + file picker; AppImage; the smaller items.
- 2026-11-15 owner's test of the installer (scratch XDG folders, then the package installed): the build worked, but
  the game's first start was windowed. The choices had gone into the scratch folder's ini while the game read the
  real one. Fix: the choices also go into the package's default ini (`pack.pack(..., settings)`), which the
  launcher copies at the first start wherever the player's folder is; the player's own ini is edited only when it
  exists. 118 unit tests. Not re-run by the owner yet.
- 2026-11-15 curses screens and file picker (evening hand-off item 3, owner: before the bootstrap is committed).
  `installer/screens.py`: the installer's questions as full screens on a terminal of 80x24 or more, over the same
  flow as the prompts (`--plain`, `TERM=dumb`, small terminals: the prompts). `installer/picker.py`: desktop portal
  through PyGObject, then zenity, kdialog; else an in-terminal browser. Checked: `tests/test_screens.py` (field,
  completion, browser, dialog order, and the real screens in a pseudo-terminal: a whole run with the dump picked
  in the in-terminal browser, and quitting); each screen captured as text at 80x24 and read (long options wrap, a
  long folder path shows its end). 126 unit tests. Not tried by the owner yet; the desktop dialogs (portal, zenity,
  kdialog) were not opened here (they would appear on the owner's desktop).
- 2026-11-15 owner's notes on the screens: the keys question shows the Ctrl+O / F2 hint too; after the build the
  installer asks "Install it now?": yes runs the package manager's install command (`pack.commands`, through sudo)
  on the plain terminal with the screens stepped aside, then Enter goes back and the result is shown; no prints the
  command as before; a failed install says so and prints the command. `--answers` never installs. 128 unit tests
  (the runner is a stand-in in tests; sudo was not run here).
- 2026-11-15 owner: build folder, disk space, clean-up. Build options ask where the build happens (the cache folder
  or another, with free space for each, checked at once; another folder gets `hylian-melodies/temp` and
  `packages`); the summary shows space needed vs free; after a successful install the installer offers to delete
  the package file; the last screen lists what stays on the computer besides the package's own files (sizes, what
  each is, which can be deleted) with one `rm -rf` line for the deletable ones (`plan.leftovers`). Folder picking
  in the dialogs (portal `directory`, zenity `--directory`, kdialog `--getexistingdirectory`) and in the in-terminal
  list ("Use this folder"). 130 unit tests; the screens captured at 80x24 and read. Bootstrap, screens and these
  are not committed yet (owner: commit after trying the screens).
- 2026-11-15 tester hand-out (owner: a few testers before the release). Leak check before it: the content guard
  over all 168 tracked files; no personal details (name, e-mail, home paths, the dump's location), no secrets, no
  Link's Awakening data, no game files; the dump's own SHA-256 is nowhere (`installer/known.py` holds only the
  extracted files' hashes, the same for everyone). `dist/hylian-melodies-0.1.0-test.zip` (git-ignored) is
  `git archive HEAD` (no history) minus the brief, every file through the guard, plus `dist/TESTING.md` (unpack,
  `sh install.sh --source .`, what it asks, removing it, what to report). Unpacked under a path with a space: tests
  pass (the tracked-files test now skips outside a git checkout), the installer starts. Left for the owner:
  `docs/DEV-ENVIRONMENT.md` describes the development machine's hardware (decide before the public release).
- 2026-11-19 GitHub (owner pushed the project and OK'd pushing updates from now on): `origin` =
  github.com/Dewey-Wilkerson/Hylian-Melodies, private. Checked: `origin/main` is this `main` (`9d9fc9d`, all 44
  commits, all 168 files, one author "Bagu"), tag `v0.1.0` on the same commit. Not on GitHub: the local revert tag
  `base-functionality` (owner's call whether to push it). The `v0.1.0` pre-release holds only `install.sh` with its
  placeholders unfilled (`@HM_TAG@` ...): no tarball, no `SHA256SUMS`, so the `curl | sh` path cannot work yet; the
  fix is `python3 tools/release.py --repo-url https://github.com/Dewey-Wilkerson/Hylian-Melodies --tag v0.1.0`
  and uploading its three files to the release (owner's OK). While the repository is private, testers need access
  to it (and a signed-in download) or the zip.
- 2026-11-19 `v0.1.0` release fixed (owner's OK): `tools/release.py --tag v0.1.0` (tarball SHA-256 7a3907f1...,
  186 files, no brief) and its three files uploaded with `gh release upload --clobber`, replacing the unfilled
  install.sh; downloaded back, `sha256sum -c SHA256SUMS` OK. The bootstrap was run with that tarball pre-cached
  (checksum checked, unpacked, installer started). While the repository is private an anonymous download is a
  404, so `curl | sh` works only once it is public; until then testers with access use the zip (`--source .`) or
  `sh install.sh --source https://github.com/Dewey-Wilkerson/Hylian-Melodies.git --ref v0.1.0` (unverified).
- 2026-11-19 before going public (owner: hardware details may stay, nothing identifying). Every file of every commit
  and every commit message searched for the host name, the user name, home paths, e-mail addresses, MAC and private
  IP addresses: none (one made-up `/home/p` in a test). `docs/DEV-ENVIRONMENT.md` lists hardware and versions only:
  kept. Package metadata: `url` (PKGBUILD, pacman, `.deb` Homepage, `.rpm` URL) is the GitHub repository, the
  licence field says `MIT` plus `LicenseRef-Personal-Copy-Of-The-Game` (the game inside) in all three formats, the
  `.deb` maintainer no longer claims root@localhost. README: an Installing section (the release's `curl | sh`
  line, a checkout, the Arch route). `releases/latest` skips pre-releases, so the README names `v0.1.0`.
- 2026-11-19 owner: remove the brief and the Arch-only install route before going public. `hylian-melodies-prompt.md`
  deleted (its rules and hard gates folded into AGENTS.md; `tools/release.py` no longer has anything to leave out);
  `packaging/arch/PKGBUILD` and its test deleted, the launcher, hooks and desktop entry moved to `packaging/`
  (`installer/pack.py`, the tests and the docs follow); `docs/packaging.md` now describes the installer's packages;
  `HM_MARCH` (read only by the PKGBUILD) left the variable list; README points at the installer only. Untracked old
  build output stays in `packaging/arch/` (git-ignored, about 9.7 GiB, the owner's to delete). 129 unit tests pass.
  The brief is then removed from every commit (history rewrite; backup bundle first).
