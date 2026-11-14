# The Arch package

`packaging/arch/PKGBUILD` builds `hylian-melodies-recomp` on your machine from your own cartridge dump. **Personal
use only: never share the package** (it contains the game).

## Build and install

```bash
cd packaging/arch
ln -s /path/to/cadence-base.xci cadence-base.xci
ln -s /path/to/prod.keys prod.keys
makepkg -si          # build and install (pacman asks for your password)
```

`makepkg` alone only builds (`hylian-melodies-recomp-<version>-x86_64.pkg.tar`, about 1.9 GiB); install it later
with `sudo pacman -U <file>`. `makepkg -sic` also deletes the build copy afterwards. Any terminal works (no window is
opened during the build). An interrupted or failed build resumes when `makepkg` runs again (without `-C`): the setup
keeps what it finished (extraction, lifting, compiled objects) in `src/`.

On the dev machine (Ryzen 7 9700X): about 2 minutes from a clean directory.

## What it installs

| Path | What |
|---|---|
| `/opt/hylian-melodies/` | the game, read-only: executable, `exefs/`, `romfs/`, `aoc/` (DLC) |
| `/usr/bin/hylian-melodies` | the launcher (`--fullscreen`, `--windowed` go to the game) |
| `/usr/share/applications/hylian-melodies.desktop` | menu entry (with a "Play fullscreen" action) |
| `/usr/share/icons/hicolor/256x256/apps/hylian-melodies.png` | the game's own icon, taken from your dump at build time |
| `/usr/share/hylian-melodies-recomp/` | default settings, where the desktop shortcut goes |

Each player's folder is `${XDG_DATA_HOME:-~/.local/share}/hylian-melodies`: a copy of the executable, links to the
game data, and their own `profile/` (saves), `hylian-melodies.ini`, `logs/`, `cache/`. Removing the package
(`pacman -R hylian-melodies-recomp`) removes the links and the executable copy and keeps saves and settings.

## Differences from the brief (section 8), all in docs/DECISIONS.md

- `/opt/hylian-melodies` instead of `/usr/share/hylian-melodies` (owner's choice: the FHS place for a self-contained,
  architecture-specific program); XDG data folder.
- XCI only (no update or DLC NSPs yet); no firmware input; no build-time shader step and so no graphical-session check.
- The VMA header is fetched at a pinned commit (`tools/fetch_vma.py`), as the brief planned: the
  `vulkan-memory-allocator` package is AUR only.
- The game's icon comes from the dump (owner's request), converted at build time; never stored in the repository.
