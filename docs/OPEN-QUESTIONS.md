# Open questions

Things that need the owner's answer, or that were parked instead of guessed. Newest last.

1. **Game version 1.5.0.** The brief says 1.5.0 is the latest; the cartridge carries the 1.4.0 update. The project
   targets 1.4.0. If you have a 1.5.0 update NSP and want it as the target, put it next to the XCI as
   `cadence-update.nsp`; the installer's version table then needs its hashes (one-time recon).
2. **FFmpeg for movies.** The `movie::` replacement needs an H.264/AAC decoder. Arch's `ffmpeg` is a GPL-enabled
   build; dynamic linking for a package built and used only on your own machine is not distribution, so this
   seems fine for personal use, but it is a GPL library at run time. Alternative: a smaller decoder (e.g. openh264,
   BSD, + an AAC decoder). Current plan: system FFmpeg, dynamically linked, like LASRecomp. Say if you object.
3. **Tests that need the game.** Regression tests that read the user's extracted files (headless boot, frame dumps)
   only run when `HM_GAME_DIR` points at an extracted install; their outputs stay outside the repo.
4. **Reference repos trust.** Running scripts from the `~/refs` checkouts against game files was blocked by the
   agent's safety check; the user offered to state trust. Until then the agent writes its own small tools.
