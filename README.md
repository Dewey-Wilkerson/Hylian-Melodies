# Hylian Melodies

A native Linux port of *Cadence of Hyrule: Crypt of the NecroDancer Featuring The Legend of Zelda* (Nintendo
Switch) made by **static recompilation**: the game's own ARM64 code is translated to C and compiled into a native
x86-64 program running on a small C runtime (Horizon OS services, NVN on Vulkan, SDL3 audio and input).

**Personal use only.** This repository contains no game code, assets or keys. The game is built on your machine from
your own cartridge dump and your own console's keys, and the resulting package must never be shared.

Status: playable; an Arch package builds from a checkout ([docs/packaging.md](docs/packaging.md)); the installer
for other distros is being designed ([docs/installer.md](docs/installer.md)). See [docs/PROGRESS.md](docs/PROGRESS.md).

- Findings about the game: [docs/RECON.md](docs/RECON.md)
- Contributing and content rules: [CONTRIBUTING.md](CONTRIBUTING.md)
- Agents: [AGENTS.md](AGENTS.md)

Not affiliated with Nintendo or Brace Yourself Games. Code: MIT ([LICENSE](LICENSE)); third-party code:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
