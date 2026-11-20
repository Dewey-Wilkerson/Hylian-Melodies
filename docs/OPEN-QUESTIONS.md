# Open questions

Things that need the owner's answer, or that were parked instead of guessed. Newest last.

1. **Game version 1.5.0** (2026-11-19, owner: stays open, look at it later; 1.4.0 remains the target, and every hook
   address in `recomp/hooks.txt` would need finding again). The brief says 1.5.0 is the latest; the cartridge carries the 1.4.0 update. The project
   targets 1.4.0. If you have a 1.5.0 update NSP and want it as the target, put it next to the XCI as
   `cadence-update.nsp`; the installer's version table then needs its hashes (one-time recon).
2. **FFmpeg for movies**: answered 2026-11-19 (owner: keep system FFmpeg, dynamically linked). The `movie::` replacement needs an H.264/AAC decoder. Arch's `ffmpeg` is a GPL-enabled
   build; dynamic linking for a package built and used only on your own machine is not distribution, so this
   seems fine for personal use, but it is a GPL library at run time. Alternative: a smaller decoder (e.g. openh264,
   BSD, + an AAC decoder). Current plan: system FFmpeg, dynamically linked, like LASRecomp. Say if you object.
3. **Tests that need the game**: settled 2026-11-19 (owner: they stay opt-in and local). Regression tests that read the user's extracted files (headless boot, frame dumps)
   only run when `HM_GAME_DIR` points at an extracted install; their outputs stay outside the repo.
4. **Reference repos trust**: answered 2026-11-19 (owner: the `~/refs` checkouts are trusted; their scripts may be run
   against the game files when useful). Running scripts from the `~/refs` checkouts against game files was blocked by the
   agent's safety check; the user offered to state trust. Until then the agent writes its own small tools.
5. **AppImage build tools**: settled 2026-11-19 without zig: the AppImage is built in a Debian 12 container (its
   C library is the old one), and the type-2 runtime is fetched at a pinned release with a SHA-256 check (MIT). Was:
   (docs/installer.md, section 4). The portable AppImage needs zig (old-glibc target) and
   the AppImage type-2 runtime, neither packaged everywhere: fetch them at pinned versions with SHA-256 checks (as
   hactool and ImGui are), or require them installed? Also: the runtime's license (MIT) and zig's (MIT) are fine.
6. **History rewrite author**: answered 2026-11-14 (owner: the pseudonym "Bagu" <bagu@hylian-melodies.invalid>). (publication step 1) Which name and e-mail the rewritten history and future commits
   carry: a GitHub noreply address (`<id>+<user>@users.noreply.github.com`) or a pseudonym.
7. **VMA header**: answered 2026-11-14 (owner: pin it). `tools/fetch_vma.py`, docs/installer.md section 9.
8. **Movies on Fedora/openSUSE** (2026-11-19, owner: settle it with a headless movie-decode check in a Fedora
   container; podman, run as its own step). Their FFmpeg decodes H.264 through `libopenh264` instead of its own decoder
   (docs/installer.md, section 9). The decoder is there; whether the game's movies play needs a run on such a system.
9. **Container check**: done 2026-11-14 (owner's OK): Debian 13, Ubuntu 26.04, Fedora 43/45, openSUSE Tumbleweed all
   build. Images and outputs removed afterwards.
10. **Game code addresses in the repository**: answered 2026-11-19 (owner: keep them; the installer's file hashes
    tie them to 1.4.0). Was (branch `in-game-gui`): `recomp/hooks.txt` and `runtime/hle/game_menu.c`
    name 1.4.0 code addresses, struct offsets and text ids (facts, like the ~10 address comments already in
    `runtime/`; no bytes, names or strings of the game). Fine to keep, or should they be located at install time
    (e.g. by a hash of each function's bytes)?
