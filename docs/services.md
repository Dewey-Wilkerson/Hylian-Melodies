# Services and stubs (M4 trace)

From the first headless boots (`HM_HEADLESS=1 HM_GAME_DIR=<install> build/hylian-melodies`, log in
`<exe dir>/logs/hylian-melodies.log`). Updated as the boot gets further. Service names and command IDs only.

## Reached so far (2026-11-13)

SDK init, both modules' constructors, the game's logger, RomFS mounted through `fsp-srv` (layout of 679 files),
time shared memory, display layer created (vi HLE), then the graphics device setup stops at the first NVN buffer
map: NVN is not implemented yet (it is LAS Recomp's `runtime/nvn/`, to be restored next).

## Services opened

| Service | Implementation | State |
|---|---|---|
| `sm:` | ipc.c | real |
| `lm` | services/am.c | logger, prints to our log |
| `appletOE` | services/am.c | ISelfController 11, 13, 14, 16, 91 and IWindowController 10 answered "ok" without effect (documented stubs) |
| `apm` | services/am.c | performance mode stub |
| `pctl`, `pctl:s`, `pctl:a`, `pctl:r` | services/misc.c | no restrictions |
| `aoc:u` | services/misc.c | to check: must report the four DLC titles |
| `fsp-srv` | services/fs.c | RomFS image laid out from `romfs/`; DLC from `aoc/<title>/` (OpenDataStorageByDataId); saves in `profile/` |
| `time:u` | services/time.c | host clock |
| `hid` | services/hid_set.c | opened; input arrives in M7 |

## HLE (host replacements by symbol)

- `nn::vi` display/layer functions: `runtime/hle/vi.c` (layer scaling mode added for this game).
- libc `mem*`/`str*`: `runtime/hle/libc.c`.
- NVN: 152 distinct calls reached as "unimplemented, returning 0" before the crash. Next: restore the NVN layer.
- `movie::` (subsdk0) and `glslc*` (subsdk1): not reached yet; resolved to "unimplemented" stubs by the loader.
