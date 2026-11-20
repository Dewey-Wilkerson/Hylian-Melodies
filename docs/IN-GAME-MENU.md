# The port's settings in the game's own Options menu (prototype)

Branch `in-game-gui`, 2026-11-19. Goal: replace the Dear ImGui overlay (F1, `runtime/ui/menu.cpp`) with rows in the
game's own Options menu. Status (2026-11-19): the Graphics page has the port's **Fullscreen** and **Frame pacing** rows (Yes/No, saved to
`hylian-melodies.ini`, applied at once) and a **Scaling filter** choice row (Sharp / Smooth / Nearest, saved, used
from the next start), in all 11 of the game's languages; the Fullscreen row follows F11 / Alt+Enter;
pages longer than the game's 8 rows get a tighter layout so the panel stays clear of the title and the description
box. Checked by scripted input and captures (English, German, Japanese, French; F11 sent with xdotool under XWayland). The
FPS-in-title and master-volume settings are gone. The overlay is still there for the rest.

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
- **Toggle update** (every frame, each toggle on the open page): brings our Fullscreen row in step after F11.
- **Page layout** (every frame): pages of more than 8 visible rows are laid out by our code, the rest by the game's.
- `HM_GAME_MENU=0` leaves the menu as the game ships it (comparison runs).

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
- **Layout** (per frame, 640x360 units): visible rows (byte +0x2c) 30 apart, the block centred on y = 183, the panel
  17 above the first row and 18 taller than the rows, 408 or 328 wide; each row gets its y through vtable +0x20. The
  free space between the title and the description box is about y 35..303: 8 rows fit, 9 at the game's pitch don't.
- **Language**: the text lookup's language argument is in/out; after the call it holds the game's current code
  (`en`, `de`, `ja`, ...), so our text follows the game's own language setting.
- **Choice row** (the Language page's type): constructor `(row (0xC0 bytes), label id, desc id, const std::string
  *key, const vector<Choice> *, std::function<void(std::string)> *, 0, 0)`.
  - A Choice is 32 bytes: `std::string` value, i32 name text id, i32 description id (-1).
  - The choices are copied to +0x90; the current index is the i32 at +0x88. With description id 0, each choice's own
    description is shown instead.
  - Left/right move the index (wrapping at the ends) and call the function with the chosen value. With an empty key,
    nothing is written to the game's config.
  - The callback wrapper's vtable comes through its own GOT slot. Its layout is the same bound member function as the
    toggles'.
- Our text borrows a game text of the same kind (row label, description, choice name) for the lookup result's style
  field (`text_style` in `game_menu.c`).
- Labels need the text lookup hook. The row's draw code calls the lookup by id, and an unknown id aborts in the
  game's text formatting.

## Plan (owner's decisions, 2026-11-19)

Rows go by topic, beside the game's own. Done when every item below is in and Dear ImGui is gone.

| Overlay setting | Decision | Work |
|---|---|---|
| Fullscreen | Yes/No row, Graphics | done, follows F11 / Alt+Enter |
| Scaling filter (3 choices, next start) | three-way row, Graphics | done (the game's choice row type) |
| FPS in the window title | removed | done (old ini lines are ignored) |
| Frame pacing | Yes/No row, Graphics | done |
| Master volume | removed | done (old ini lines are ignored; `HM_AUDIO_GAIN` stays for tests) |
| Rebinding (16 buttons, keyboard and gamepad, reset) | new Controls page | a button row in the main Options list opening a page (button rows: label = the current keys through the text hook; A starts a "press a key" capture in host code, as `input.c` does for the overlay; a Reset row) |
| About (version, folder, keys) | version on the title screen | the port's version beside the game's own version text |
| F1 / Minus+Plus | freed | remove the shortcut; Minus+Plus reach the game like on a Switch |

Also:
- Our text in all 11 of the game's languages (en, ja, de, fr, cafr, es, uses, it, kr, sc, tc): done for the rows so
  far, drafted by the agent; a native check is wanted. New rows add their text to the table in `game_menu.c`
  (`tests/test_recomp.py` checks every text has every language).
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
