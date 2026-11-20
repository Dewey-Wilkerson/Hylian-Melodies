# Hylian Melodies

A native Linux port of *Cadence of Hyrule: Crypt of the NecroDancer Featuring The Legend of Zelda* (Nintendo
Switch) made by **static recompilation**: the game's own ARM64 code is translated to C and compiled into a native
x86-64 program running on a small C runtime (Horizon OS services, NVN on Vulkan, SDL3 audio and input).

**Personal use only.** This repository contains no game code, assets or keys. The game is built on your machine from
your own cartridge dump and your own console's keys, and the resulting package must never be shared.

Status: playable from the title through the first dungeons at a steady 60 fps; early test release. See
[docs/PROGRESS.md](docs/PROGRESS.md) and [docs/KNOWN-ISSUES.md](docs/KNOWN-ISSUES.md).

## Installing

You need your own cartridge dump (`.xci`, carrying the 1.4.0 update) and your own console's `prod.keys`, an x86-64
computer with a Vulkan 1.3 graphics driver, and about 15 GiB of free space while it builds. Supported: Arch (and
CachyOS, Manjaro...), Debian 12 and 13, Ubuntu 24.04 and 26.04, Fedora 43 and newer, openSUSE Tumbleweed.

```sh
curl -fsSL https://github.com/Dewey-Wilkerson/Hylian-Melodies/releases/download/v0.1.0/install.sh | sh
```

The script downloads this release's source, checks its SHA-256 and starts the installer, which asks for your dump
and keys (both are only read where they are), tells you which packages your system lacks, builds the game in a few
minutes and makes a package for your package manager (pacman, apt, dnf or zypper). It never needs root itself; at
the end it offers to install the package with sudo. Run it again later to rebuild, change settings or remove it.

From a checkout instead: `git clone https://github.com/Dewey-Wilkerson/Hylian-Melodies && cd Hylian-Melodies &&
sh install.sh --source .` What the package puts where: [docs/packaging.md](docs/packaging.md).

Playing: the overlay menu is F1 (or Minus and Plus together on a gamepad); keys and buttons are in
[docs/controls.md](docs/controls.md). Saves and settings live in `~/.local/share/hylian-melodies/`.

## More

- Findings about the game: [docs/RECON.md](docs/RECON.md)
- Contributing and content rules: [CONTRIBUTING.md](CONTRIBUTING.md)
- Agents: [AGENTS.md](AGENTS.md)

Not affiliated with Nintendo or Brace Yourself Games. Code: MIT ([LICENSE](LICENSE)); third-party code:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
