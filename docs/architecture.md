# Architecture

How *Cadence of Hyrule* 1.4.0 for Switch becomes a native Linux x86-64 program. Background and numbers:
[RECON.md](RECON.md). Decisions: [DECISIONS.md](DECISIONS.md).

## Pipeline (run once on the user's machine)

1. **check / extract** (`installer/`, hactool built by `tools/build_hactool.py`): XCI -> verified `exefs/`,
   `romfs/` (base + 1.4.0 merged) and `aoc/<title>/` (DLC). See [installer.md](installer.md).
2. **lift** (`recomp/gen.py`): `main` and `sdk` NSOs -> C, one C function per guest function, into
   `<temp>/generated/{main,sdk}/`. Every file starts with the content marker (never committed).
3. **compile** (`tools/build_game.py`): clang -O1, `-march=x86-64-v2` by default (generic); `--march v3|native` optimizes for the building computer only. Ninja, lld.
4. **shaders**: translate and pre-build the game's shader variants (needs the GPU: graphical session).
5. **cleanup**.

## CPU: the lifter (`recomp/`)

From LAS Recomp (MIT): hand-written A64 decoder (`lifter.py`), portable NEON/FP lowering to C helpers that match the
Switch's rounding and FMA (`simd_c.py`, `runtime/simd.h`, `runtime/simd_fp.h`), NSO loader (`nso.py`).

`gen.py` partitions `.text` into functions from `.eh_frame_hdr`, exported symbols, `R_AARCH64_RELATIVE` targets,
BL targets and ADR/ADRP+ADD code addresses, splitting at every external branch target until a fixpoint. Direct
calls become C calls (`f_<addr>(c)`), tail branches `musttail` calls, indirect branches go through `rt_dispatch`
(address table, `runtime/dispatch.c`). Jump tables are resolved by `jumptables.py`, a small concrete interpreter of
the integer subset switch lowering uses (no Unicorn); a function with any `br` table also gets a fallback that
dispatches to any of its instructions, so a missed table is slow, never wrong.

Scale (1.4.0): `main` 20,052 functions, 715 jump tables; `sdk` 33,586 functions, 515 jump tables; zero unsupported
instructions. Generation takes ~10 s on 16 threads.

Guest addresses equal host addresses: `main` at `0x7000000000`, `sdk` at `0x7004000000` (`runtime/rt.h`).

## Runtime (`runtime/`, M4+)

Based on LAS Recomp's runtime, stripped of everything specific to Link's Awakening:

- kernel (host threads for guest threads, SVCs, sync objects, memory), loader (relocations, imports bound to host
  HLE functions first), IPC + services (`fs` with saves in `profile/`, `hid`, `audout`, `time`, `acc`, `appletOE`,
  `vi`, `set`, offline `nifm`/`bsd`), HLE for `movie::` (FFmpeg), glslc (glslang) and heap helpers;
- NVN recorded and replayed on Vulkan, Maxwell shader translator, SDL3 window;
- audio: FMOD's AudioOut buffers -> SDL3 audio stream, paced like the console (the rhythm clock).

## Packaging (`packaging/arch/`, M9)

Brief section 8: the game read-only in `/usr/share/hylian-melodies/`, a launcher that gives each user a writable
copy-and-symlink folder in `~/.local/share/hylian-melodies/`, pacman hooks for desktop entry and cleanup.
