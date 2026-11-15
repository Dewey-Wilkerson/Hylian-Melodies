# Installer

Two layers:

1. **The player-facing installer** (design below, not built yet): a `curl | sh` bootstrap that fetches a pinned,
   checksummed copy of this repository and starts a terminal UI (Python, stdlib `curses`). The UI asks for the
   player's own dump and keys, checks them early, lets them choose how to install (system package, loose folder,
   AppImage, later Flatpak) and with which options, runs the setup and records what it did, so running it again
   offers update / change options / uninstall.
2. **The setup engine** `python3 -m installer` (exists): check, extract, lift, compile, cleanup into an install
   folder, with JSON events on stdout. The UI drives it; the PKGBUILD drives it today. See the second half.

Hard rules for both: never upload anything; no telemetry; never run `sudo`/`pkexec` from a script (the UI prints the
package manager command for the player to run); the keys and the dump are read in place and never copied, printed
or logged; the only network access is fetching this project's source and its pinned build inputs (Dear ImGui,
the VMA header, hactool source), each checked against a SHA-256 or a commit ID.

## Part 1: player-facing installer (design, 2026-11-14)

Owner's decisions this follows (docs/PROGRESS.md, "Next (publication and installer)"): test against a private git
repository before going public (public later by changing one default URL); every build generic (x86-64-v2) by
default with CPU-specific builds opt-in; expose every player-relevant flag and environment variable with an
explanation; no machine-ID binding.

```
curl -fsSL <url>/install.sh | sh               bootstrap (POSIX sh, ~200 lines)
  └─ checks: Linux x86-64, python3 >= 3.11, curl or wget, tar, sha256sum
  └─ fetch tag vX.Y.Z tarball -> verify SHA-256 -> ~/.cache/hylian-melodies/src/vX.Y.Z/
  └─ exec python3 -m installer.tui </dev/tty    terminal UI (stdlib curses)
       ├─ existing install found (manifest)? -> update / change options / repair / uninstall
       ├─ dependencies (per distro: what is missing and the command to get it; never installs)
       ├─ inputs: XCI + prod.keys (file picker) -> early `check`
       ├─ output: system package | loose folder | AppImage | Flatpak (later)
       ├─ build options, launch options (each with an explanation)
       ├─ summary -> confirm
       ├─ progress (setup engine's JSON events) -> output-specific packaging
       └─ done: how to start it; the package manager command to run, if any; manifest written
```

### 1. Bootstrap `install.sh`

- **Shape.** POSIX `sh` (dash, busybox ash, bash in sh mode); the whole script is a `main "$@"` function called on
  the last line, so a truncated download runs nothing. `set -eu`. Arguments through `curl ... | sh -s -- --flag`.
- **Prompts via `/dev/tty`.** stdin is the script itself, so every question reads from `/dev/tty` and the UI is
  started with `</dev/tty`. No usable `/dev/tty` (CI, cron): stop with a message pointing to the non-interactive mode
  (`--answers FILE`, section 2).
- **Pinned and checked.** The release tool (`tools/release.py`, to write) fills two constants into the published
  script: `HM_TAG=vX.Y.Z` and `HM_SHA256=<tarball sha256>`. The bootstrap downloads
  `${HM_REPO_URL}/archive/refs/tags/$HM_TAG.tar.gz` (one default URL: the private repository during testing, the
  public one later), checks the SHA-256 with `sha256sum` (or `shasum -a 256`), and refuses on mismatch. A matching
  tarball already in the cache is reused (offline rerun).
- **Where.** `~/.cache/hylian-melodies/src/$HM_TAG/` (`$XDG_CACHE_HOME` honoured). Nothing else is written by the
  bootstrap.
- **Overrides.**
  - `--source PATH`: a local checkout (development); no checksum, the UI shows "unverified source".
  - `--source URL --ref REF`: `git clone --depth 1 --branch REF` with the player's own git credentials (how the
    private repository is reached: SSH key or credential helper; the script never asks for or stores a token).
  - `--tag vX.Y.Z --sha256 HEX`: another release.
  - `--help`, `--version`, `--print-only` (show what would be fetched and run, then stop).
- **Not done here:** installing packages, root, PATH changes, shell rc edits.

### 2. Terminal UI `python3 -m installer.tui`

- **Stdlib only.** `curses` for the screens, `subprocess` for the setup engine and helpers. A model/view split: an
  `Install` plan object (inputs, output, options) and pure functions that validate it, separate from the curses
  screens, so tests drive the model without a terminal.
- **Fallbacks.** `TERM=dumb`, no curses or a terminal under 80x24: the same questions as plain numbered prompts.
  `--answers FILE.json`: no questions at all (tests, scripted installs); every field of the plan, validated the same.
- **Screens.**
  1. *Welcome*: what this is, personal use only, needs the player's own cartridge dump and console keys; nothing is
     uploaded. Source and tag shown (and "unverified" for `--source`).
  2. *Existing install* (only when the manifest lists one, section 6).
  3. *Dependencies*: build tools and libraries found or missing, distro detected from `/etc/os-release` (`ID`,
     `ID_LIKE`); for missing ones the exact command for that distro (`installer/deps.py`, from the table in
     section 9; a release without SDL3 is told so; unknown distros get the generic names). The player runs it in another terminal and presses "check
     again". Python is stdlib only: NSO segments are unpacked by our own LZ4 block decoder
     (`recomp/lz4block.py`), so `python-lz4` is not needed.
  4. *Inputs*: base XCI (later NSP update/DLC), `prod.keys` through the file picker (section 3). Then at once
     `python3 -m installer --until check` against a scratch destination, so a wrong file, a missing key revision or
     too little disk is reported before anything long runs.
  5. *Output* (section 4), with what each one means for updates, removal and where saves live.
  6. *Build options* and 7. *Launch options* (section 5).
  8. *Summary*: every choice, disk space needed vs free, then "Install".
  9. *Progress*: one line per setup step with a bar from the `progress` events, the message text from
     `installer/messages.py`, the log path; on `error`, the message and "retry" (the setup resumes) / "quit".
  10. *Done*: how to start the game, the package manager command to run (system package), manifest written.

### 3. Picking the dump and keys

Order, first that works:

1. **Desktop portal** (`org.freedesktop.portal.FileChooser.OpenFile`) through the `gdbus` command (glib, present on
   practically every desktop): call, then wait for the `Response` signal with `gdbus monitor`. Native dialog on GNOME,
   KDE and others, also inside sandboxes. Stdlib Python has no D-Bus; a hand-written D-Bus client is not worth it.
2. `zenity --file-selection` or `kdialog --getopenfilename` when present.
3. **In-terminal browser** (curses list: folders, `.xci`/`.nsp`/`.keys` highlighted, `~` and recent folders as
   shortcuts). Used directly when there is no graphical session (`$DISPLAY` and `$WAYLAND_DISPLAY` unset, or
   `$SSH_CONNECTION` set).

A typed path (with Tab completion) is always accepted. The files are used where they are: the setup reads the XCI
in place and hactool gets the keys with `-k <path>` (already so in `installer/hactool.py`); the manifest records the
paths and the dump's SHA-256 (facts only), never the keys' contents.

### 4. Outputs

All four start from the same setup-engine run into a staging folder; they differ in the final layout and in who
owns removal. Each built output contains the game, so the UI repeats: **for this computer's owner only, never
share it**.

| Output | Needs | Game files | Player data | Update / remove |
|---|---|---|---|---|
| **System package** (default on Arch, Debian/Ubuntu, Fedora/openSUSE) | the distro's packaging tool | `/opt/hylian-melodies` | `${XDG_DATA_HOME:-~/.local/share}/hylian-melodies` (launcher, as today) | rerun the UI to build the new package; remove with the package manager (saves kept) |
| **Loose folder** (any distro, no root) | nothing extra | the chosen folder (default `~/Games/Hylian Melodies`) | inside the same folder | rerun the UI; uninstall asks whether to keep `profile/` (saves) and the ini |
| **AppImage** (portable) | `mksquashfs`; zig (fetched, pinned) | inside the image | XDG data folder, like the package | replace the file; uninstall removes it and its menu entry |
| **Flatpak** (last) | `flatpak-builder` | inside the app, built locally, never exported to a remote | the app's data folder | `flatpak uninstall` |

- **System package** (the first output built; section 9 has the packages each distro needs). One path for all
  three formats: the UI runs the setup engine itself into a staging folder (dump and keys read in place), then a
  packer wraps that tree. The bootstrap's source is a tarball without `.git`, so the developer PKGBUILD
  (`git+file://` source, `git describe` version, its own setup run in `$srcdir`) is not what the UI calls; it stays
  for building from a checkout.
  - Arch: a generated minimal PKGBUILD whose `package()` hard-links the staged tree (`makepkg` gives the pacman
    metadata and fakeroot); same `.install` hooks, `PKGEXT=.pkg.tar`.
  - Debian family: `dpkg-deb --root-owner-group -Znone --build` (no fakeroot, no `dpkg-dev`; the data is already
    compressed); maintainer scripts generated from the `.install` hooks' logic.
  - Fedora/openSUSE: `rpmbuild -bb` from a generated spec, staged tree as its source, uncompressed payload
    (`%define _binary_payload w0.ufdio`), `%defattr(-,root,root)`.
  - Run-time dependencies are never a hand-written list of library packages (their names carry soname versions
    that change per release, e.g. the FFmpeg ones): they are derived from the built executable. pacman: the fixed
    names of section 9; deb: each `DT_NEEDED` library resolved with `ldd`, then `dpkg-query -S` names its package;
    rpm: rpmbuild's own ELF dependency generator. A Vulkan driver is a recommendation, not a dependency, outside
    Arch (no common virtual name).
  - Same package name (`hylian-melodies-recomp`), paths, launcher and version (`VERSION`, plus the tag) everywhere.
    The UI prints e.g. `sudo pacman -U <file>` / `sudo apt install ./<file>` / `sudo dnf install <file>`.
- **Loose folder.** The install folder itself, with the executable at its top, plus (optional) a menu entry and icon
  in `~/.local/share/applications` and `~/.local/share/icons`. The launcher logic (player folder = install folder)
  becomes a mode of `hylian-melodies.sh` instead of a second script.
- **AppImage.** The portable variant: always x86-64-v2; built with `zig cc -target x86_64-linux-gnu.2.28` so it runs
  on old glibc; SDL3, ffmpeg and shaderc built or copied in and found through `$ORIGIN` rpaths; Vulkan loader and
  driver from the host. Squashfs plus the AppImage type-2 runtime, both pinned by version and SHA-256. Open: where
  zig and the runtime come from and whether that download is acceptable (docs/OPEN-QUESTIONS.md).
- **Flatpak.** A manifest on `org.freedesktop.Platform`, built with `flatpak-builder --user --install`. After the
  others work.

### 5. Options

Every option has a one-paragraph explanation shown beside it, from one registry (`installer/options.py`) that
also generates the env-var list in the docs; a test checks the registry against the code (section 7).

**Build options** (changing one recompiles; extraction is kept):

| Option | Values | Explanation shown |
|---|---|---|
| CPU level | **v2** (default), v3, native | "Generic" runs on any x86-64 CPU since about 2009, also on other computers. "Optimize for this computer's CPU" (v3/native) may be a little faster and will not start on an older CPU. v3 is offered only when this CPU has it; AppImage is always v2. Passed as `--march`. |
| Keep build cache | **off**, on | Keeps the generated C and compiled objects (several GB) in the temp folder: an update or option change then recompiles only what changed. |
| Work folder | default `~/.cache/hylian-melodies/temp` | Where extraction and compilation happen; free space shown. |
| Parallel jobs | default: all cores | Fewer keeps the computer usable during the compile. |

**Launch options** (no rebuild; written to the menu entry and to `<player dir>/launch.env`):

- *Start in fullscreen* (`--fullscreen` / `--windowed`) and a "Play fullscreen" menu action (exists today).
- The player group of `HM_*` environment variables, from the env-var audit (docs/PROGRESS.md, publication step 6:
  192 `getenv("HM_...")` in `runtime/` sorted into player / troubleshooting / developer, dead LAS Recomp leftovers
  removed). Player and troubleshooting ones are listed, troubleshooting under "Advanced"; developer ones are not.
- `launch.env` holds `KEY=value` lines; the launcher reads it (parsed, never `source`d; only `HM_*` keys accepted),
  so starting from a terminal and from the menu behaves the same. Settings the in-game menu already covers
  (`hylian-melodies.ini`: video, audio, controls) are not duplicated; the UI points to the menu (F1).

### 6. Manifest, update, uninstall

`${XDG_DATA_HOME:-~/.local/share}/hylian-melodies/installs.json`, written atomically after each successful run:

```json
{"format": 1, "installs": [{
  "id": "…", "output": "package|folder|appimage|flatpak", "location": "…",
  "version": "0.2.0", "tag": "v0.2.0", "source": {"url": "…", "sha256": "…"},
  "inputs": {"base": {"path": "…", "sha256": "…"}, "keys": {"path": "…"}},
  "build": {"march": "v2", "keep_cache": false}, "launch": {"fullscreen": false, "env": {}},
  "files": ["~/.local/share/applications/hylian-melodies.desktop", "…"],
  "package": {"name": "hylian-melodies-recomp", "file": "…"}}]}
```

On a rerun the UI lists these installs and offers:

- **Update**: a newer tag (the bootstrap fetched it) -> rebuild; the setup's per-step source hashes already redo
  only lift/compile when the project changed and keep the extraction when the dump did not.
- **Change options**: launch options are rewritten at once; build options recompile.
- **Repair**: rerun the setup's checks (hashes of the extracted files) and fix what is missing.
- **Uninstall**: folder and AppImage: remove what `files` and `location` list, asking about saves; package: print the
  remove command; Flatpak: `flatpak uninstall`. The entry leaves the manifest.

Files the manifest does not list are never deleted.

### 7. Tests and checks

- Bootstrap: `sh -n` and a run under `dash` against a local tarball server (`--source`, checksum mismatch refused,
  truncated script runs nothing); `shellcheck` when installed.
- UI model: unit tests with `--answers` plans (valid/invalid, CPU level vs CPU flags, AppImage forces v2).
- Options registry vs code: every `getenv("HM_...")` in `runtime/` is in the registry with a group, and every
  registry entry exists in the code.
- Outputs: each built into a temporary `HOME`; `.deb`/`.rpm` contents listed and compared with the Arch package's
  file list; installing them is the owner's check on such a system.
- Developer runs of the UI use a scratch `HOME`/`XDG_*` so nothing lands in the owner's real menu.

### 8. Order of work

Owner, 2026-11-14: the first version gets the system packages right; the other outputs follow.

1. Dependencies: done 2026-11-14 (`installer/deps.py`, `python3 -m installer.deps`; own LZ4 decoder, VMA pinned,
   container check). Left: movies on Fedora/openSUSE on a real system.
2. Packers on the staged tree: pacman, `.deb`, `.rpm` (section 4), each built into a temporary `HOME` and its file
   list compared with the others.
3. UI model, `--answers`, plain prompts (enough to drive 1 and 2); manifest; update/uninstall for packages.
4. Options registry + env-var audit (publication step 6); `launch.env` in the launcher.
5. Bootstrap and `tools/release.py`; test against the private repository (push only with the owner's OK then).
6. Curses screens and the file picker; loose folder; then AppImage; Flatpak last.

### 9. System packages (checked 2026-11-14)

What the build and the game need, found by reading `tools/build_game.py`, `tools/build_hactool.py`, the fetch
tools, the PKGBUILD, the runtime's includes and the executable's `DT_NEEDED`. Names were checked against the
distros' package databases, then **tried in containers** (podman, 2026-11-14): the install command below on a bare
image, then hactool and the game built from the same generated C, the unit tests, and each `DT_NEEDED` library
traced back to its package. All five build, link with nothing missing and pass the tests.

**Supported for the system package** (Python >= 3.11; clang >= 17 from the distro's repositories):

| Distro | From | Built with (container) |
|---|---|---|
| Arch and derivatives | rolling | SDL3 3.4.20, FFmpeg 9.0, clang 23 (the dev machine) |
| Debian | 13 "trixie" | SDL3 3.2.10, FFmpeg 7.1, clang 19, shaderc 2025.2, Python 3.13 |
| Ubuntu | 26.04 | SDL3 3.4.2, FFmpeg 8.0, clang 21, Python 3.14 |
| Ubuntu 24.04 (and what is built on it) | with our own SDL3 | SDL3 3.4.20 built from source and linked in, FFmpeg 6.1, clang 18, Python 3.12 |
| Debian 12 "bookworm" | with our own SDL3 and shaderc | both built from source and linked in, FFmpeg 5.1, clang 19 (`clang-19`), Python 3.11 |
| Fedora | 43 (tried: 43, 45) | SDL3 3.4.20, FFmpeg 7.1 / 9.0, clang 21 / 23, Python 3.14 / 3.15 |
| openSUSE | Tumbleweed | SDL3 3.4.20, FFmpeg 9.0, clang 23, Python 3.13 |

**Older releases: libraries built from source.** Two tools in the style of `tools/build_hactool.py` (pinned
commits, nothing vendored), run by the UI when `installer/deps.py` reports `sdl3: own` or `shaderc: own`; the game
is then linked against the result statically and the installed game needs no package for it:

| Library | Tool, build option | When | Pinned | Time (dev machine) |
|---|---|---|---|---|
| SDL3 | `tools/build_sdl3.py`, `build_game.py --sdl3 DIR` | the release has no SDL3 package and `pkg-config sdl3` finds none (Ubuntu 24.04, Debian 12) | release-3.4.20 | under a minute |
| shaderc | `tools/build_shaderc.py`, `build_game.py --shaderc DIR` | the release's shaderc package cannot be used (Debian 12) | v2026.4 with the glslang, SPIRV-Tools and SPIRV-Headers revisions it names | 23 s on 16 threads (about 5 CPU-minutes) |

Tried end to end on bare Debian 12, Ubuntu 24.04 and Debian 13 images, with `installer/deps.py` itself choosing
what to install: its command, a second check with nothing missing, the libraries, hactool, the game (links, no
`libSDL3` / `libshaderc` among `DT_NEEDED` where they are our own), the unit tests. The container builds were not
run; the same static build made on the dev machine was (20 s: window, audio, shader compiles, movies, title screen).

- **SDL3** only supports what it finds headers for, so its build needs: `cmake libwayland-dev libxkbcommon-dev
  libegl-dev libdecor-0-dev libx11-dev libxext-dev libxrandr-dev libxcursor-dev libxi-dev libxfixes-dev libxss-dev
  libxtst-dev libpipewire-0.3-dev libpulse-dev libasound2-dev libudev-dev libdbus-1-dev`. The build stops unless a
  window system and an audio system made it in; with these it has Wayland, X11, PipeWire, PulseAudio, ALSA, udev and
  D-Bus. SDL loads those desktop libraries at run time by name, so they are not in the executable's `DT_NEEDED`:
  the `.deb` lists them as recommendations. An SDL3 the player installed themself is used as it is.
- **shaderc on Debian 12**: its `libshaderc1` has 36 undefined glslang symbols and names no library that provides
  them, so nothing links against it. Our build needs only `cmake` on top of the compiler.
- **clang on Debian 12**: the runtime needs clang 17 or newer (`__builtin_elementwise_fma`); Debian 12's `clang` is
  14, but `clang-19` and `lld-19` are in its repositories. The command names those, and the setup puts
  `/usr/lib/llvm-19/bin` first on its own PATH (`deps.use_newer_clang`) so `clang`, `clang++` and `ld.lld` are found.
- Debian 12's Vulkan headers (1.3.239) predate one optional call; the runtime guards it.
- ImageMagick 6 on both has `convert`, not `magick`: the icon step takes either.
- The two tools' output folders may have spaces in their path (tried); `pkg-config` is not used for them.

The same two builds are what the AppImage needs later.

**The check asks for capabilities, never for package names**, so a wrong or renamed package cannot produce a false
"missing": commands with `shutil.which`; libraries with `pkg-config --exists` per module; Python modules by import.
The names below are used only to print the one command for the player.

| Need (how it is checked) | Arch | Debian / Ubuntu | Fedora | openSUSE |
|---|---|---|---|---|
| `git` (pinned fetch of hactool, Dear ImGui, VMA) | `git` | `git ca-certificates` | `git` | `git` |
| `python3` >= 3.11, `import curses` | `python` | `python3` | `python3` | `python3 python3-curses` |
| `clang`, `clang++`, version 17+ | `clang` | `clang` | `clang` | `clang` |
| `ld.lld` | `lld` | `lld` | `lld` | `lld` |
| `ninja` | `ninja` | `ninja-build` | `ninja-build` | `ninja` |
| `make`, `cc` (hactool) | `make gcc` | `make gcc` | `make gcc` | `make gcc` |
| C++ standard headers (a one-line compile) | `gcc` | `g++` | `gcc-c++` | `gcc-c++` |
| `pkg-config` | `pkgconf` | `pkgconf` | `pkgconf-pkg-config` | `pkgconf-pkg-config` |
| `strip` | `binutils` | `binutils` | `binutils` | `binutils` |
| pc: `sdl3` | `sdl3` | `libsdl3-dev` | `SDL3-devel` | `SDL3-devel` |
| pc: `libavformat libavcodec libavutil libswscale` | `ffmpeg` | `libavformat-dev libavcodec-dev libavutil-dev libswscale-dev` | `libavformat-free-devel libavcodec-free-devel libavutil-free-devel libswscale-free-devel` | `'pkgconfig(libavformat)' 'pkgconfig(libavcodec)' 'pkgconfig(libavutil)' 'pkgconfig(libswscale)'` |
| pc: `vulkan` (headers 1.3+, loader) | `vulkan-headers vulkan-icd-loader` | `libvulkan-dev` | `vulkan-headers vulkan-loader-devel` | `vulkan-devel` |
| pc: `shaderc` | `shaderc` | `libshaderc-dev` | `libshaderc-devel` | `shaderc-devel` |
| icon: `magick` or `convert` | `imagemagick` | `imagemagick` | `ImageMagick` | `ImageMagick` |
| packer | `base-devel` (`makepkg`, fakeroot) | `dpkg-deb` (always there) | `rpm-build` | `rpm-build` |

Notes from the container runs:

- Debian/Ubuntu were installed with `--no-install-recommends`, so the list is complete without recommendations;
  `ca-certificates` is needed for the HTTPS fetches on a bare system.
- openSUSE's FFmpeg development packages carry the major version in their name (`ffmpeg-9-libavcodec-devel`), so
  the command uses the `pkgconfig(...)` capabilities, which zypper resolves; `python3-curses` resolves to
  `python313-curses` the same way. `rpm-build` installs on a bare image; it hit a solver conflict once when
  installed last, after everything else (not looked into: recheck when the `.rpm` packer is written).
- The run-time packages `ldd` + `dpkg-query -S` / `rpm -qf` find from the built executable: Debian 13 `libsdl3-0
  libavformat61 libavcodec61 libavutil59 libswscale8 libvulkan1 libshaderc1`; Ubuntu 26.04 the same with
  `libavformat62 libavcodec62 libavutil60 libswscale9`; Fedora `SDL3 libav{format,codec,util}-free libswscale-free
  vulkan-loader libshaderc`; openSUSE `libSDL3-0 libavformat63 libavcodec63 libavutil61 libswscale10 libvulkan1
  libshaderc_shared1`. The versioned names are why the list is derived, not written down (section 4).
- Debian 13's SDL 3.2 has no `SDL_SavePNG`: the screenshot helper (debug captures only) writes a `.bmp` there.
- `curl` is not on a bare Debian/Ubuntu; whoever ran `curl | sh` has it.

At run time: the libraries above (derived, section 4), a Vulkan 1.3 driver, and optionally `fontconfig` (`fc-match`:
the menu's system font) and `xdg-user-dirs`. For the UI: `curl` or `wget`, `tar`, `sha256sum`; `gdbus` for the
portal file picker (`glib2` / `libglib2.0-bin` / `glib2`), optional because of the fallbacks.

**Open points found by this pass** (docs/OPEN-QUESTIONS.md 7-9):

1. *VMA header: settled.* The `vulkan-memory-allocator` package is AUR only on Arch (it was installed on the dev
   machine, which hid this) and missing on Debian 12, and the packaged versions run from 3.2 to 3.5. The header is
   now fetched at a pinned commit (v3.5.0, MIT) by `tools/fetch_vma.py`, like Dear ImGui: no package on any distro.
2. *Movies on Fedora and openSUSE.* The game's movies are H.264 + AAC (docs/RECON.md). Debian, Ubuntu and Arch
   have FFmpeg's own `h264` decoder. Fedora's and openSUSE's FFmpeg decode H.264 through `libopenh264` (AAC, VP9 and
   Vorbis are built in); on Fedora 45 the real `openh264` library comes along by default from the Cisco repository.
   So a decoder is there, but whether it plays these files is untested: it needs a run on such a system.
3. *Compiled, not run.* The containers have no GPU or display: the builds link and the unit tests pass, the game was
   not started in them.
4. `tools/build_game.py` ignored a failing `pkg-config` (missing library -> a confusing compile error much later):
   fixed, it stops and names the modules.

## Part 2: the setup engine `python3 -m installer`

Turns the user's own dump and keys into an install folder. Stdlib-only Python;
one JSON event per line on stdout; full log in `<temp>/run-<time>/logs/install.log`; exit status 0 only when the
result is `ok`.

```
python3 -m installer --base cadence-base.xci [--update cadence-update.nsp] --keys prod.keys --dest DIR
                     [--temp DIR] [--root DIR] [--hactool EXE] [--imgui DIR] [--march v2|v3|native] [--until STEP]
```

### Steps

| Step | What it does |
|---|---|
| check | inputs exist; keys file sane (count only, never values; needs master key revision 0x0A); Python >= 3.11; free space; containers open with the keys |
| extract | unpack the XCI secure partition (or NSP) into `<temp>/work/nca`; parse every CNMT; verify each needed NCA against its CNMT SHA-256 and the known-good table (`installer/known.py`); title keys from the cart's tickets into a private temp HOME; merge base + 1.4.0 update into `exefs/` + `romfs/`; verify ExeFS hashes and the RomFS manifest; extract the four DLC RomFS into `aoc/<title id>/` |
| lift | ARM64 -> C into `<temp>/generated` (`recomp/gen.py`) |
| compile | `tools/build_game.py` (clang, lld, Ninja; `--march`, default x86-64-v2) into the game executable |
| cleanup | remove work files |

No shader step: shaders are compiled on first use (docs/DECISIONS.md).

### Install folder

```
<dest>/
  exefs/  romfs/  aoc/<title id>/     extracted, verified game files
  hylian-melodies                     the game executable
  hm-install.json                     finished steps, version, extract sub-steps, source hashes (resume)
```

### Resume

Each step records completion in `hm-install.json`; a rerun skips finished steps (event `resume`). Inside extract,
sub-steps (`unpack`, `hashes`, `game`, `aoc`) are recorded too, and partial output lives in `.partial*` folders that
are renamed into place only after verification, so a run killed at any point resumes cleanly. Lift and compile also
record a hash of their project sources (compile: and the CPU level) and run again when it changed.

### Events

`start {steps}`, `step {step,msg}`, `progress {step,pct}` (integer, only on change), `info|warning|error
{msg,args,text}` with `msg` an ID from `installer/messages.py`, `end {result: ok|error, ...}`.

### Keys

The keys file is read by hactool only (via `-k`); the installer reads it just to count entries and check which key
names exist. hactool runs through `installer/hactool.py` with a private HOME under `<temp>/work/hactool-home` (0700,
wiped at start and end), so it never sees `~/.switch` and the title-key file never outlives a run. Its output is
filtered before logging.
