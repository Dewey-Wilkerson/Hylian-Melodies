# Hylian Melodies: agent guide

Native Linux port of *Cadence of Hyrule* (Switch) by static recompilation: the game's ARM64 code is lifted to C,
compiled for x86-64 and run on a C runtime standing in for Horizon OS, NVN (on Vulkan) and audio (SDL3). Personal use.
The full brief is `hylian-melodies-prompt.md`; this file is the working summary. A fresh agent reading this file,
`docs/PROGRESS.md`, `docs/KNOWN-ISSUES.md` and `docs/OPEN-QUESTIONS.md` must be able to continue.

## Rules that override everything (brief section 2)

1. **No game content in the repo**: no binaries, disassembly, generated C, assets, strings, symbol names, keys,
   firmware. Facts only (sizes, SHA-256, build/title IDs, versions). Details: `CONTRIBUTING.md`. In doubt: don't
   commit, add to `docs/OPEN-QUESTIONS.md`.
2. **Never print keys.** `prod.keys` and title keys never reach output, logs, commands or files in the repo.
   hactool prints key values in warnings: only call it through `installer/hactool.py`.
3. **Publish nothing** (push, GitHub, AUR, uploads) without the owner's approval in the current conversation.
4. **No sudo, no package install**, no writes outside the project dir, `~/.cache/hylian-melodies/`,
   `~/.local/share/hylian-melodies/` (and `~/refs/` for reference checkouts). Never modify the owner's dump/keys.
5. **Licenses**: copy only MIT/BSD/ISC/zlib/Apache-2.0 code, with a `THIRD_PARTY_NOTICES.md` row in the same commit.
   No GPL/AGPL (SwitchRECOMP, Unicorn, ...) without approval.
6. Stop and ask only for the hard gates (brief section 9); otherwise decide, log one line in `docs/DECISIONS.md`,
   continue.

## Layout

```
installer/       setup stages (check, extract, lift, compile, shaders, cleanup); JSON events on stdout
recomp/          lifter (ARM64 -> C) and install-time patch location (no game bytes)
runtime/         C runtime: loader, kernel, IPC services, NVN-on-Vulkan, audio, input, saves
tools/           build_hactool.py, fetch_refs.sh, check_content.py
packaging/arch/  PKGBUILD, launcher, .install hooks, desktop entry (docs/packaging.md); packaging/*.ini/*.svg
docs/            RECON, DECISIONS, PROGRESS, OPEN-QUESTIONS, KNOWN-ISSUES, architecture, building, installer
tests/           unittest suites (python3 -m unittest discover -s tests)
.githooks/       pre-commit content guard
```

## Where things live on this machine

- Game inputs (owner's, read-only): `cadence-base.xci`, `prod.keys` in the project root (git-ignored).
- Dev install / work dir: `~/.cache/hylian-melodies/` (`recon/` = M0 scratch extraction, `dev/` = installer dest,
  `toolchain/` = built hactool, `temp/` = installer temp and logs).
- Reference checkouts: `~/refs/` (`tools/fetch_refs.sh`).

## Commands

```bash
git config core.hooksPath .githooks          # once per clone
python3 -m unittest discover -s tests        # all tests
python3 tools/check_content.py --staged      # what the hook runs
python3 tools/build_hactool.py --out ~/.cache/hylian-melodies/toolchain/hactool
python3 recomp/gen.py main ~/.cache/hylian-melodies/dev/exefs/main 0x7000000000 ~/.cache/hylian-melodies/gen/main
python3 recomp/gen.py sdk  ~/.cache/hylian-melodies/dev/exefs/sdk  0x7004000000 ~/.cache/hylian-melodies/gen/sdk
python3 tools/build_game.py --gen ~/.cache/hylian-melodies/gen --out ~/.cache/hylian-melodies/build --target game
HM_GAME_DIR=~/.cache/hylian-melodies/dev HM_RUN_SECONDS=20 HM_WINDOW_SHOT=800 ~/.cache/hylian-melodies/build/hylian-melodies
    # log: <build>/logs/hylian-melodies.log; captures: <game dir>/build/window_*.png (outside the repo)
python3 -m installer --base cadence-base.xci --keys prod.keys --dest ~/.cache/hylian-melodies/dev \
    --temp ~/.cache/hylian-melodies/temp --hactool ~/.cache/hylian-melodies/toolchain/hactool/hactool
```

## Facts about the game (from docs/RECON.md)

- Not Unity: custom C++ engine on nn::gfx/NVN, FMOD Studio statically linked, SDK 6.5.0.
- Cartridge holds base 1.0.0 + update 1.4.0 (`01000B900D8B0800`, title-key crypto, ticket on cart) + 4 DLC. Target 1.4.0.
- Lift `main` + `sdk` (~45k functions); `subsdk0` = movie (HLE), `subsdk1` = glslc (HLE), `rtld` dropped.
- Audio: FMOD -> `audout` (AudioOut API) -> host SDL3. Network: always offline.

## Known traps

- devkitPro hactool reads `~/.switch/prod.keys` by default and prints key values: always via `installer/hactool.py`.
- The 1.4.0 patch NCA uses rights-ID crypto: extraction needs the cart's ticket title key (handled in a temp HOME).
- Running scripts from `~/refs` against game files may be blocked by the agent safety check; write own tools.
- The runtime takes SIGTERM: end test runs with `HM_RUN_SECONDS` (and `timeout -s KILL` as a backstop).
- `pkill -f`/`pgrep -f <pattern>` match the shell running them (it killed the agent's shell twice); find processes
  by exact name (`pgrep -x`, `ps -eo comm`) or put the command in a script file.
- When adapting LAS Recomp code: rename its user-visible strings and `LARECOMP_*` variables at once, and drop
  anything keyed to Link's Awakening's shader words, hashes or game data.

## Status

See `docs/PROGRESS.md`.
