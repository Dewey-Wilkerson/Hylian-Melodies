# M0 Reconnaissance

Done 2026-11-12 with the devkitPro hactool and throwaway scripts outside the repo, on files extracted to
`~/.cache/hylian-melodies/recon/` (never inside the repository). Only facts (sizes, hashes, IDs, versions, counts)
are recorded here.

## 1. The cartridge dump

`cadence-base.xci`: 2,172,823,040 bytes, 4 GB cartridge, root HFS0 with `update`, `logo`, `normal` (empty) and
`secure` partitions.

The `secure` partition holds more than a base game:

| Title ID | Type | Version | Content |
|---|---|---|---|
| `01000B900D8B0000` | Application | v0, display **1.0.0** | Program NCA (701,890,560 B, SDK 6.6.0), Control, Manual |
| `01000B900D8B0800` | Patch | v393216, display **1.4.0** | Program NCA (1,056,330,752 B, SDK 6.7.0, title-key crypto, ticket on the cart), Control, Manual |
| `01000B900D8B1001`..`1004` | AddOnContent (4) | v393216 | PublicData NCAs (DLC data) |

The `update` partition is a Switch system update (219 NCAs), i.e. firmware, not a game update.

**Conclusion**: this is a cartridge that ships the 1.4.0 update and the four DLC packs. Extracting the patch Program
NCA against the base (BKTR) with the cart's title key yields the full 1.4.0 ExeFS and RomFS. **No separate update
file is needed for 1.4.0.** The brief says the latest version is 1.5.0; the cartridge carries 1.4.0. I target
**1.4.0** (what you have). If a 1.5.0 update NSP exists and you want it, see `OPEN-QUESTIONS.md`.

Known-good hashes (SHA-256) of the input file, recorded by the installer's check stage (`installer/known.py`):
see that file; the values are hashes of your official files only.

## 2. ExeFS (1.4.0, merged)

| Module | NSO size | .text | .rodata | .data | .bss | Build ID (first 20 B) |
|---|---|---|---|---|---|---|
| `rtld` | 7,391 | 6,640 | 3,344 | 640 | 3,456 | `09aa0f157b8cf44df373510612a0452a4803b2ab` |
| `main` | 6,005,772 | 8,167,536 | 2,189,368 | 368,056 | 40,563,272 | `7179a4bd112b6c656c274987aca710b800000000` |
| `sdk` | 5,232,210 | 5,359,104 | 6,511,340 | 394,296 | 801,736 | `b2872a7bcc589969fb7afb8e372414e4fac5a750` |
| `subsdk0` | 3,564,776 | 3,633,424 | 2,464,580 | 202,040 | 1,166,024 | `305ef5b2e6cd40196faf6e42e21b222d386cb81b` |
| `subsdk1` | 4,151,576 | 5,038,848 | 2,880,572 | 907,832 | 9,672 | `8d073b25b9abda677e6967cef9ef6070178e374e` |

`main.npdm`: 1,508 bytes. NSO SHA-256 values are in `installer/known.py`.

What the modules are (from SDK middleware tags and the import tables):

- `sdk`: NintendoSDK 6.5.0 (`nnSdk`, NVN, libz).
- `main`: the game. Statically links NintendoSDK `gfx` (nn::gfx over NVN), NintendoWare Font, libcurl, NEX 4.6.2
  (online), and **FMOD Studio** (the audio engine).
- `subsdk0`: NintendoSDK `multimedia` (the `movie::` player: MP4/WebM demux, decoders).
- `subsdk1`: NintendoSDK `glslc` (the online GLSL compiler for NVN).

## 3. Unity / IL2CPP? **Refuted** (high confidence)

- No Unity player, no `libil2cpp`, no `global-metadata.dat` or any `Data/` tree in RomFS, no Unity strings in any
  module.
- The game's code in `main` is native C++ (RTTI type names of an engine of its own), linked with nn::gfx and FMOD.
- Assets use Nintendo formats (BNTX textures, BNSH NVN shader binaries, BFFNT fonts) and FMOD Studio banks.

So this is a **custom C++ engine on nn::gfx/NVN with FMOD**, the same class of program as the reference ports, and
the reference approach applies directly. Nothing Unity-specific is needed.

### Audio (the rhythm-game clock)

- FMOD Studio is statically linked in `main`. Music and effects are FMOD banks in RomFS.
- FMOD outputs through **`audout:u`** (the game imports the `nn::audio` AudioOut API: open default out, append and
  release PCM buffers, volume) and **not** through the audio renderer (`audren:u`). The AudioIn API is imported too
  (microphone support in FMOD; can be a "no device" stub).
- Consequence: the host only has to take FMOD's PCM buffers and play them through SDL3. FMOD mixes in game code, so
  timing is driven by how fast the host releases buffers. This is the simplest possible audio path and gives direct
  control over latency, which is good news for M6.

### Graphics

- The only NVN import of `main` is the bootstrap loader; nn::gfx gets every NVN entry point through it, as in
  LASRecomp (`runtime/hle/nvn_boot.c` pattern).
- Shaders ship precompiled for Maxwell (BNSH in RomFS). `main` also imports the glslc API, so some shaders may be
  compiled from GLSL at run time; if so, the host can compile that GLSL with glslang directly to SPIR-V and skip
  Maxwell translation for those (to confirm in M4/M5).

### Video

- `movie::` (from `subsdk0`) plays H.264 + AAC MP4 files (1280x720, 30 fps). Replace at the `movie::` API level with a
  host decoder (LASRecomp does this with FFmpeg), so `subsdk0` need not be lifted.

## 4. RomFS layout (generic)

1.8 GiB, 679 files.

| Kind | Count | Size |
|---|---|---|
| XML data (level and game data) | ~560 | small |
| FMOD Studio banks | 40 | 1.1 GiB |
| text data (music-related) | 32 | <1 MiB |
| MP4 videos (H.264/AAC) | 14 | 607 MiB |
| zlib-compressed binary data | 14 | |
| NVN shader binaries (BNSH) | 8 | |
| fonts (BFFNT) | 6 | |
| textures (BNTX) | 5 | |
| colour lookup tables | 4 | |

DLC content: partly in RomFS directories of the patch, partly in the four AddOnContent NCAs (the game mounts them
with `nn::fs::MountAddOnContent`; the host must serve them, so the installer extracts those too).

## 5. Services the game needs

From a static pass over the `nn::*` imports of `main` (function counts per namespace), mapped to Horizon services:

| Area (imports) | Service(s) | Plan |
|---|---|---|
| `nn::os` (56) | kernel SVCs | host threads, events, mutexes (LASRecomp kernel) |
| `nn::audio` (33) | `audout:u`, `audin:u` | AudioOut -> SDL3; AudioIn -> no devices |
| `nn::hid` (24) | `hid` | SDL3 gamepad + keyboard |
| `nn::fs` (18) | `fsp-srv` | RomFS from the extracted folder, saves under `profile/`, AoC mounts |
| `nn::account` (14) | `acc:u0` | one fixed local user |
| `nn::time` (7) | `time:u` | host clock |
| `nn::oe` (6) | `appletOE` | focus/operation mode messages |
| `nn::vi` (5) | `vi:m` | SDL3 window |
| `nn::swkbd` (5) | applet | stub or host text input |
| `nn::settings` (2) | `set` | language/region |
| `nn::socket` (41), `nn::nifm` (8), `nn::ssl` (2), `nn::nsd` (1), NEX, libcurl | `bsd:u`, `nifm:u`, `ssl`, `nsd` | **offline**: report no network |
| `nn::aoc` (1), `nn::ec` (1) | `aoc:u`, `ec` | report all four DLC owned (they are on your cartridge) |
| `nn::crypto` (5), `nn::util`, `nn::mem`, `nn::diag`, `nn::err` | in-process / `err` | lifted SDK code; `err` stub |
| `movie::` (28), `glslc*` (8) | subsdk0, subsdk1 | HLE at API level |

The SDK module itself contains client code for many more services; only those reached at run time matter, and M4's
service-call trace will confirm this list.

## 6. Lifting scale

Functions listed in `.eh_frame_hdr` (leaf functions without unwind info come on top):

| Module | Functions | Lift? |
|---|---|---|
| `main` | 19,534 | yes |
| `sdk` | 25,951 | yes |
| `subsdk0` | 9,834 | no (movie HLE), lift later only if needed |
| `subsdk1` | 11,533 | no (glslc HLE) |
| `rtld` | tiny | no (host links modules) |

About 45,000 functions and ~13.5 MB of code to lift: the same order as LASRecomp's Link's Awakening (main + sdk,
which it lifts in minutes on a desktop) and far below TotK, so the totk-scale rewrite of the lifter is not needed up
front. Expected generated C: a few hundred MB, compile in minutes with 16 threads. Disk need is small: about 2 GiB
extracted + ~2 GiB generated/objects; the 40 GiB gate is not an issue (2.2 TiB free).

## 7. Recommendation

**Build on LASRecomp** (MIT), which this repository already imported at `579fdad`:

- Lifter: LASRecomp's `gen.py`/`lifter.py`/`simd_c.py`, moved to `recomp/`, with its Unicorn jump-table resolver
  replaced by our own static resolver (as totk did) so no GPL code is used. Add `LDXP/STXP` if the game needs them.
- Runtime: LASRecomp's kernel, IPC, fs/hid/audio services, NVN-on-Vulkan with the Maxwell translator and shader
  preparation, Linux platform layer. Strip everything specific to Link's Awakening (randomizer, cosmetics, hooks,
  address tables). Replace its audio renderer path with an AudioOut -> SDL3 path, since this game uses `audout`.
- Installer and packaging: totk-pc-recomp's shape (Python stdlib `installer/` with JSON events and resume,
  `tools/build_hactool.py`), and the Arch package from the brief.
- Kernel write tracking: **not used**. CoH is a light 2D/2.5D game; LASRecomp's Vulkan path works without it. No
  kernel minimum beyond what glibc/Vulkan need (decision in `DECISIONS.md`).

Where this game differs from the reference ports:

1. FMOD over AudioOut instead of the audio renderer: simpler, and latency is under our control.
2. nn::gfx in `main` and glslc available at run time: possible GLSL shaders alongside BNSH.
3. Online stack (NEX, curl, sockets) must be cleanly "offline".
4. DLC lives in AddOnContent NCAs that the installer must extract and the fs service must mount.
5. SDK 6.5.0 is older than LA's; IPC command IDs and struct layouts of that era must be matched.

Biggest risks:

- **Shaders**: Maxwell translation correctness for this game's BNSH (LASRecomp's translator was tuned for one game).
- **Threading**: FMOD's mixer thread and the game's frame loop rely on Horizon scheduling; audio buffer release
  timing must be paced like the console (48 kHz, fixed buffer sizes) or music drifts.
- **SDK 6.5 differences** in lifted SDK code paths (TLS layout, SVC usage) vs. what the runtime implements.
- Effort: the whole M0-M10 plan is many weeks of work; this is a long multi-session project.

Milestone plan (rough effort, agent-time):

| Milestone | Effort |
|---|---|
| M1 skeleton, guardrails | hours |
| M2 hactool + check/extract (incl. AoC, title key) | hours |
| M3 lift main+sdk, link | 1-3 sessions |
| M4 headless boot to engine init | several sessions |
| M5 NVN on Vulkan to title screen | many sessions (largest) |
| M6 audio | 1-2 sessions |
| M7 input, saves | 1-2 sessions |
| M8 playable | open-ended |
| M9 packaging | 1 session (can be done early against a partial game) |
| M10 polish | open-ended |

The approach is feasible. Continuing to M1.
