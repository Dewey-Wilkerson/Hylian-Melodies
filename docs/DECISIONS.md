# Decisions

One line each, newest last. Format: date, decision, reason.

- 2026-11-12: Target game version **1.4.0** (the update on the user's cartridge); no separate update file. Reason: RECON.md section 1.
- 2026-11-12: Build on **LASRecomp** (MIT) for lifter and runtime; totk-pc-recomp's shape for installer and packaging. Reason: RECON.md section 7.
- 2026-11-12: Keep the existing git history (LAS Recomp import `9c20fa2`) instead of re-initialising; M1 removes the imported tree and re-adds adapted pieces with attribution. Reason: preserves provenance of the MIT code we adapt.
- 2026-11-12: Removed LAS Recomp's `.github/workflows` (CI and release for its own project). Reason: no remote, nothing is published.
- 2026-11-12: No Unicorn (GPL-2.0) anywhere, not even in tests; jump tables are resolved by our own static pass. Reason: brief 2.4.
- 2026-11-12: Kernel write tracking (soft-dirty / PAGEMAP_SCAN, kernel >= 6.7) is **not** used; no kernel minimum. Reason: small 2D game, LASRecomp's Vulkan path works without it.
- 2026-11-12: Lift `main` and `sdk` only; replace `subsdk0` (movie) and `subsdk1` (glslc) at the API level; drop `rtld`. Reason: RECON.md sections 3 and 6.
- 2026-11-12: Audio through `audout` -> SDL3 audio stream, no audio renderer emulation. Reason: the game's FMOD uses AudioOut.
- 2026-11-12: Network is always "unavailable" (nifm reports no connection, sockets fail). Reason: personal offline use; no online features needed.
- 2026-11-12: hactool runs with explicit `-k`, `--disablekeywarns --suppresskeys`, filtered output, and `HOME` set to a private 0700 temp dir (so it never reads the user's `~/.switch`). Title keys from the cart's ticket go into a 0600 `title.keys` in that temp home, deleted right after, never on the command line or in logs. Reason: hactool prints key values in warnings; command lines are visible in `ps`.
- 2026-11-12: The project's own code is MIT. Reason: brief 2.4 default.
- 2026-11-12: Tests use the standard library `unittest` (pytest is not installed). Reason: fewer dependencies.
- 2026-11-12: A resolved jump table's switch lists only its targets and calls `rt_jt_miss` (fatal) otherwise; the all-instruction-label fallback stays only for unresolved computed branches. Reason: a 50k-instruction function in `main` with 17 tables made clang use 19 GB under the all-label scheme.
- 2026-11-12: Game code is linked statically into one executable (not LAS's separate game library). Reason: one binary to copy per user (brief 8.1), no loader for a game library needed.
- 2026-11-12: Launcher and pacman hooks written early (during M3) because they are independent of the game; M9 still owns the PKGBUILD and the package build. Reason: used compile wait time.
- 2026-11-13: Save mounts journal file creation too: a `CreateFile` leaves `<file>.new` until the next commit; a mount rolls back files that still have one. Reason: a killed run left a committed-looking zero-filled save that crashed the next boot (the Switch rolls uncommitted creates back).
- 2026-11-13: Headless renderer = NVN front end + `runtime/nvn/null_backend.c` (records, never draws); M5 swaps in the Vulkan backend. Reason: lets M4 run the engine's init without a GPU path.
- 2026-11-13: Input is answered at the `nn::hid` function level (LAS Recomp's approach), and the controller-support applet returns "player 1" at once. Reason: the game blocks in that applet when no controller is reported.
- 2026-11-13: Side study: delivering CoH as a Crypt of the NecroDancer (Synchrony) mod is not worth it, neither as the route nor as a side project (docs/NECRODANCER-MOD-FEASIBILITY.md). Reason: a mod is a full logic rewrite on a run-based host engine; the port already lifts, links and boots.
- 2026-11-13: The movie HLE answers end of stream with status `0x2000` (default; `HM_MOVIE_EOS_CODE` overrides). Reason: the game compares the extractor's result with that value; anything else made it wait forever on the splash video.
