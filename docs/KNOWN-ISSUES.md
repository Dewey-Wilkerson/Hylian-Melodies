# Known issues

- The game does not run yet: the boot stops at graphics setup (NVN not implemented). See PROGRESS.md.
- Input is a placeholder (`runtime/hle/input_stub.c`); rumble is ignored.
- The software keyboard returns the initial text unchanged (`runtime/hle/swkbd.c`).
- The shared-font service (`pl:u`) and input bindings were removed with LAS Recomp's UI; re-add if the trace shows
  the game needs them.
- Some LAS Recomp comments in restored runtime files still describe Link's Awakening behaviour.
