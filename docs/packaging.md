# The package

The installer (`sh install.sh`, or `python3 -m installer.tui` in a checkout) builds `hylian-melodies-recomp` on your
computer from your own cartridge dump, as a package for your system's package manager: pacman, `.deb` (apt) or
`.rpm` (dnf, zypper). **Personal use only: never share the package** (it contains the game). `installer/pack.py`
lays out one package tree for all three formats; the distro's own tool (makepkg, dpkg-deb, rpmbuild) wraps it.

## What it installs

| Path | What |
|---|---|
| `/opt/hylian-melodies/` | the game, read-only: executable, `exefs/`, `romfs/`, `aoc/` (DLC) |
| `/usr/bin/hylian-melodies` | the launcher, `packaging/hylian-melodies.sh` (`--fullscreen`, `--windowed` go to the game) |
| `/usr/share/applications/hylian-melodies.desktop` | menu entry with a "Play fullscreen" action (`packaging/hylian-melodies.desktop`) |
| `/usr/share/icons/hicolor/...` | the game's own icon, taken from your dump at build time; else the project's |
| `/usr/share/hylian-melodies-recomp/` | default settings (`packaging/hylian-melodies.ini`), where the desktop shortcut goes |
| `/usr/share/licenses/hylian-melodies-recomp/LICENSE` | the code's licence (MIT) |

Install and remove hooks: `packaging/hylian-melodies-recomp.install` (the same shell functions for all three
formats). Each player's folder is `${XDG_DATA_HOME:-~/.local/share}/hylian-melodies`: a copy of the executable,
links to the game data, and their own `profile/` (saves), `hylian-melodies.ini`, `logs/`, `cache/`. Removing the
package removes the links and the executable copy and keeps saves and settings.

## Choices behind it (docs/DECISIONS.md)

- `/opt/hylian-melodies` (the FHS place for a self-contained, architecture-specific program); XDG data folder.
- XCI only (no separate update or DLC NSPs yet); no firmware input; no build-time shader step.
- The VMA header is fetched at a pinned commit (`tools/fetch_vma.py`): the `vulkan-memory-allocator` package is
  AUR only on Arch.
- The game's icon comes from the dump, converted at build time; never stored in the repository.
- Until 2026-11-19 an Arch-only developer `PKGBUILD` built the same package from a checkout; the installer does all
  three formats now, so it was removed.
