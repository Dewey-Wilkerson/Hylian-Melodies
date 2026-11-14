# Reference notes

How each reference project splits the work between lifter, runtime, per-game patches and installer, in my own
words. Checkouts live in `~/refs/` (outside the repo; `tools/fetch_refs.sh` recreates them at the pinned commits).
Studied 2026-11-12.

| Repo | Commit studied | License |
|---|---|---|
| [SwitchRECOMP](https://github.com/SwitchRECOMP-Dev/SwitchRECOMP) | `713c861` (2026-11-06) | AGPL-3.0 + NOTICE terms; `runtime/snxvk/` GPL-3.0+ |
| [LASRecomp](https://github.com/peiikai/LASRecomp) | `579fdad` (2026-11-06) | MIT |
| [SavageWindRecomp](https://github.com/Revivedx/SavageWindRecomp) | `740b180` (2026-11-12) | MIT |
| [totk-pc-recomp](https://github.com/valentderah/totk-pc-recomp) | `7a37fc3` (2026-11-10) | MIT |
| [super-odyssey-pc-recomp](https://github.com/Simon3Sarkis/super-odyssey-pc-recomp) | `c82448c` (2026-11-12) | MIT |

This project began from an import of LASRecomp at `579fdad`, the same commit as the reference checkout
(`~/refs`). That import commit was dropped from the history on 2026-11-14 (it held Link's Awakening data); the
owner keeps the old history as a local backup bundle. Read LAS Recomp code from the reference checkout.

## SwitchRECOMP (read only: AGPL, see CONTRIBUTING.md)

- **Lifter**: a general Python recompiler (`switchrecomp.py` driver, `a64.py` decoder, `codegen.py` C emitter,
  `nxloader.py` NSO/NRO loader) meant to handle any game without per-game work.
- **Runtime**: a broad C emulation of Horizon: kernel objects, real IPC services, a Maxwell GPU model with an OpenGL
  renderer (and an optional GPL Vulkan one), audio, video.
- **Per-game patches**: minimal; the goal is generality.
- **Installer**: a GUI that runs the recompiler on a user's extracted `exefs/romfs`.
- Takeaway: the "emulate at the IPC level, model the GPU" approach is general but heavy. Nothing is copied from it.

## LASRecomp (the base for this project)

- **Lifter**: `tools/gen.py` + `lifter.py` (hand-written A64 decoder) + `simd_c.py` (NEON/FP to C helpers that match
  the Switch's rounding and fused multiply-add). One C function per guest function, found from `.eh_frame_hdr` plus
  call targets. Indirect branches go through an address-keyed table (`runtime/dispatch.c`). Jump tables are resolved
  by single-stepping with **Unicorn** (GPL-2.0): we must not inherit that.
- **Runtime**: SDK boundary is mixed: real `sm:` IPC services for some things (fs, hid, audio, time, acc, am) plus
  HLE replacements of SDK functions by symbol (`runtime/hle/`: libc, heaps, input, movie over FFmpeg, NVN bootstrap).
  Own NVN implementation recorded into command lists and replayed on Vulkan (Linux/Windows) or Metal, with its own
  Maxwell shader translator (Maxwell to GLSL to SPIR-V via shaderc). Guest threads are host threads.
- **Per-game patches**: `tools/patches.py` checks the original instruction word before patching, keyed by version
  tables (`runtime/game_addresses/`); hooks call `rt_hook()` so behaviour changes without regenerating.
- **Installer**: an ImGui start screen that runs a frozen generator + bundled zig to build the game code library on
  the player's machine (`runtime/gamebuild.c`, resumable). Linux ships as an AppImage writing to
  `~/.local/share/lasrecomp/`.
- Build gotchas from its README: generated C needs clang GNU extensions; FFmpeg is linked dynamically for LGPL
  reasons; the game code is a separate library (`build/lasgame.*`) loaded by the runtime.

## SavageWindRecomp (legal posture model)

- Same split as LASRecomp (it is a fork), applied to Breath of the Wild. `docs/SAVAGE-WIND.md` keeps a running log of
  every change from the base, per area, which makes rebasing on upstream tractable.
- `CONTRIBUTING.md` spells out the content boundary: no game code, assets, keys or generated output; patches stored
  as logic keyed by build ID.
- `docs/linux.md`: everything per user in `~/.local/share/savagewind`, `*_DATA_ROOT` override, SDL3 gamepads with
  hidraw permissions noted, glibc 2.35 baseline.

## totk-pc-recomp (installer and packaging model)

- **Lifter** (`recomp/`): LASRecomp's decoder and NEON lowering rewritten for scale: parallel worker processes,
  bounded memory, **own symbolic jump-table resolver instead of Unicorn** (keeps GPL out), LDXP/STXP, NZCV and hot
  registers kept in C locals, `subsdk*` loaded, `rtld` dropped (the host links modules). Guest address == host
  address below 2^39.
- **Runtime**: SDK boundary at the `nn::*` function level (from MacNativeGames); only `audren:u` and `sm:` are real
  IPC. Threads modelled on Horizon's three-core scheduler with preemption (spin-wait gates, async preemption).
  NVN front end replayed into Vulkan at submit time; pool coherency through write watch (Windows `MEM_WRITE_WATCH`).
  Shaders through the Ryujinx translator built with .NET NativeAOT as a separate process (`tools/build_xlate.py`).
- **Per-game patches**: `recomp/patches-v*.txt` per version, checked against original words.
- **Installer** (`installer/`, stdlib-only Python): stages check -> fonts -> extract -> lift -> compile -> prepare
  shaders -> clean up, JSON events on stdout, a GUI on top, `totk-install.json` records finished steps for resume.
  hactool is built from a pinned commit by `tools/build_hactool.py` (shallow fetch of the commit, patches, `make`,
  banner check with an empty `HOME` so the builder's keys are never read). `tools/fetch_refs.sh` pins upstream
  checkouts and skips what is already at its pin. `tools/check_content.py` guards commits. Its Arch package (not in
  the repo) is specified in our brief, section 8.

## super-odyssey-pc-recomp

- Another LASRecomp descendant (Windows first, Linux AppImage experimental). Own NSP/XCI reader
  (`tools/test_nxpkg.c`, `test_nxcrypto.c`), so no hactool at runtime; one data image; game code built at install
  time; every shader compiled at install time from a pipeline seed list; per-version patches in
  `tools/odyssey_patches.py` with porting helpers between versions (`port141.py`, `match141.py`) that locate code by
  structure, which is the pattern our brief asks for (patch sites located at install time, not stored as bytes).

## What this project takes from where

| Piece | Source of ideas | Code reuse |
|---|---|---|
| Lifter core (decoder, NEON lowering, dispatch) | LASRecomp | MIT, adapted with attribution in `THIRD_PARTY_NOTICES.md` |
| Jump tables without Unicorn | totk-pc-recomp's approach | own implementation |
| Runtime kernel/services/NVN/Vulkan | LASRecomp | MIT, adapted |
| Installer stages, JSON events, resume | totk-pc-recomp | own implementation, same shape |
| `build_hactool.py`, `fetch_refs.sh`, `check_content.py` | totk-pc-recomp | own implementation modelled on them |
| Content rules, CONTRIBUTING | SavageWindRecomp / totk | own text |
| Install-time patch location by structure | super-odyssey-pc-recomp | own implementation |
| Arch package | brief section 8 | own implementation |
