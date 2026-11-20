# The port's settings in the game's own Options menu (prototype)

Branch `in-game-gui`, 2026-11-19. Goal: replace the Dear ImGui overlay (F1, `runtime/ui/menu.cpp`) with rows in the
game's own Options menu. Status: **one row works** — "FULLSCREEN" (Yes/No) at the end of the game's Graphics page,
with its own description in the game's text box. Flipping it switches fullscreen at once and writes `fullscreen` to
`hylian-melodies.ini`. Checked by scripted input and window captures (1856x1044 windowed, 3840x2161 after flipping).
Not checked by hand with real presses. The overlay is still there, unchanged.

## How it works

- `recomp/hooks.txt` lists function hooks (`<module> <address> <host function>`). `recomp/gen.py` loads it by default,
  so the installer's lift step needs no change. A hooked function `f_X` becomes `f_X_orig`, and `f_X` calls
  `<host function>(Cpu *c, GuestFn orig)`. The generator refuses an address that isn't a function start.
- `runtime/hle/game_menu.c` holds the two hooks:
  - **Options screen builder** (one function builds every Options page): it runs the original, then finds the page whose
    first row has the Disco Floor label (text id 70), makes a row of the game's own toggle class with the game's own
    constructor, and appends it to that page's row vector.
  - **Text lookup** (text id -> {i32 style, `std::u32string`}): ids from `0x484d0000` up are ours. For one of ours it
    runs the original with a borrowed id of the game's (label or description), so the style field is right, then
    swaps in our text.
- `HM_GAME_MENU=0` turns the row off (comparison runs).

## What was learned (1.4.0; facts only)

- Menus are built in code, not data. The lifted `main` has no symbols for them. They were found from text ids in
  `localization.xml` (`<text id=...>`). A function that loads most `options_*` ids as immediates is the builder.
- **Builder**: makes the rows with `operator new(0x90)` and a row-class constructor, pushes each `unique_ptr<Row>` into
  a vector per page, and moves the pages into a vector of pages at `this+0x68` (24 bytes per page). Pages, in order:
  - main list (buttons);
  - Gameplay (toggles);
  - Graphics (toggles);
  - Audio (two sliders);
  - Language (a list row and a toggle).
- **Toggle constructor** `(row, label id, desc id, const std::string *key, std::function<void(bool)> *, default, 0, 0)`:
  - label id at +0x08, desc id at +0x0C;
  - key copied to +0x30, function copied to +0x50;
  - value byte at +0x88, default at +0x89;
  - it reads the value from the game's config by key.

  With an empty key the toggle skips the config (no stray entry in the game's settings or save). It just flips +0x88
  and calls the function, so our value lives only in our ini.
- **Callback**: the game's toggles take a bound member function. The wrapper's vtable is read through a GOT slot. Its
  buffer holds the function pointer at +8, the this-adjust at +0x10 and the object at +0x18. An HLE address
  (`hle_register`) works as the function pointer, so the game calls straight into host code.
- **Layout is automatic**: the panel grows for an eighth row and the selection and description box follow. No drawing
  code was touched.
- Labels need the text lookup hook. The row's draw code calls the lookup by id, and an unknown id aborts in the
  game's text formatting.

## Plan (owner's decisions, 2026-11-19)

Rows go by topic, beside the game's own. Done when every item below is in and Dear ImGui is gone.

| Overlay setting | Decision | Work |
|---|---|---|
| Fullscreen | Yes/No row, Graphics | done; keep it in step when F11 / Alt+Enter switch (remember the row, set +0x88, refresh) |
| Scaling filter (3 choices, next start) | three-way row, Graphics | find a multiple-choice row type (the Language page's list row first); description says "next start" |
| FPS in the window title | removed | drop the row, `show_fps` in settings and the ini, the title code |
| Frame pacing | Yes/No row, Graphics | same toggle pattern as Fullscreen |
| Master volume | removed | drop `volume` (the game's Sound and Music sliders stay); ignore old ini lines |
| Rebinding (16 buttons, keyboard and gamepad, reset) | new Controls page | a button row in the main Options list opening a page (button rows: label = the current keys through the text hook; A starts a "press a key" capture in host code, as `input.c` does for the overlay; a Reset row) |
| About (version, folder, keys) | version on the title screen | the port's version beside the game's own version text |
| F1 / Minus+Plus | freed | remove the shortcut; Minus+Plus reach the game like on a Switch |

Also:
- Our text in all 11 of the game's languages (en, ja, de, fr, cafr, es, uses, it, kr, sc, tc). The hook gets the
  language string. The agent drafts the translations; a native check is wanted.
- Check the pause menu's Options (same builder or another one?).
- Then drop Dear ImGui: `runtime/ui/menu.cpp`, `imgui_glue.cpp`, `tools/fetch_imgui.py` and its patch, and the build
  and packaging steps that fetch it. Keep the input-capture and window-request parts the hooks use.
- Addresses stay in the repository (open question 10, answered).

## Reproducing

```bash
python3 recomp/gen.py main ~/.cache/hylian-melodies/dev/exefs/main 0x7000000000 ~/.cache/hylian-melodies/gen-igg/main
python3 tools/build_game.py --gen ~/.cache/hylian-melodies/gen-igg --out ~/.cache/hylian-melodies/build-igg --target game
```

Then run from the title screen: gear (`left`, `a`) -> Options (`a`) -> two `down` -> Graphics (`a`) -> seven `down`.
In a test run: `HM_INPUT_SCRIPT=1700:left,1760:a,1960:a,2200:down,2300:down,2400:a,2600:down,...` with
`HM_RUN_SECONDS=80` (startup speed varies; leave margin). Menus need about 50 frames between presses.
