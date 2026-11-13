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
| M5 Graphics | next |
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
