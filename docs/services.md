# Services and stubs (M4)

From headless boots: `HM_HEADLESS=1 HM_HEADLESS_SECONDS=30 HM_GAME_DIR=<install> build/hylian-melodies`; the log
is `<exe dir>/logs/hylian-melodies.log`. Service names and command IDs only.

## Where the boot gets (2026-11-13)

SDK init -> both modules' constructors -> RomFS mounted -> display layer -> graphics device (recorded, not drawn) ->
all textures and audio objects loaded -> save file created -> controller check -> two splash videos decoded and
played to the end -> network found offline -> main-menu music playing -> **main loop running**: 904 frames presented
in a 30 s run, no crash, no unimplemented call.

## Services the game opens

| Service | Implementation | Notes |
|---|---|---|
| `sm:` | `ipc.c` | real |
| `lm` | `services/am.c` | the game's log lines go to our log |
| `appletOE` | `services/am.c` | documented stubs, answered "ok" with no effect: ISelfController 11 (operation-mode change notification), 13 (focus handling mode), 14 (restart message), 16 (out-of-focus suspending), 91; IWindowController 10 (acquire foreground rights). None changes what the game does on PC. |
| `apm` | `services/am.c` | performance mode: normal |
| `pctl`, `pctl:s`, `pctl:a`, `pctl:r` | `services/misc.c` | no restrictions; IParentalControlService 1 (initialise) answered "ok" |
| `acc:u0` | `services/acc.c` | one local user |
| `aoc:u` | `services/misc.c` | to verify in M8: the four DLC must be listed |
| `fsp-srv` | `services/fs.c` | RomFS laid out from `romfs/`, DLC from `aoc/<title>/`, saves in `profile/` with journaled creates and writes |
| `time:u` | `services/time.c` | host clock |
| `hid` | `services/hid_set.c` + `hle/input.c` | player 1 connected, no buttons until M7 |
| `audout:u` | `services/audio.c` | FMOD's output: opened at 48 kHz stereo; tuning in M6 |
| `nifm:u` | `services/net.c` | offline: requests never accepted, "no connection" |
| `bsd:u` | `services/net.c` | sockets fail with "network down" |

## Host replacements (HLE by symbol)

- `nn::vi` display/layer (`hle/vi.c`), libc `mem*`/`str*` (`hle/libc.c`), software keyboard (`hle/swkbd.c`:
  returns the initial text).
- NVN: LAS Recomp's front end with `nvn/null_backend.c` (headless; M5 brings the Vulkan backend).
- `nn::hid` state, vibration and the controller-support applet (`hle/input.c`, `hle/controller_applet.c`).
- `movie::` over FFmpeg (`hle/movie.c`): the extractor reports end of stream with the movie library's status
  `0x2000`, which this game checks for (LAS Recomp's game accepted any non-zero value).
- `glslc*` (subsdk1): never called so far.
