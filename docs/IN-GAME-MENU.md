# The port's settings in the game's own Options menu

Built on branch `in-game-gui` 2026-11-19, on `main` since v0.2.0. Goal: replace the Dear ImGui overlay (F1) with rows
in the game's own Options menu. Status (2026-11-19): the Graphics page has the port's **Fullscreen** and **Frame pacing** rows (Yes/No, saved to
`hylian-melodies.ini`, applied at once) and a **Scaling filter** choice row (Sharp / Smooth / Nearest / Pixel-perfect, saved, used
from the next start; Sharp <-> Pixel-perfect applies at once); a **Controls** page (its button takes the place of the game's Change Controllers, 2026-11-20) rebinds every Switch button
to a key or a gamepad button, with Reset to defaults, in all 11 of the game's languages; the Fullscreen row follows F11 / Alt+Enter;
pages longer than the game's 8 rows get a tighter layout so the panel stays clear of the title and the description
box. Checked by scripted input and captures (English, German, Japanese, French; F11 sent with xdotool under XWayland). The
FPS-in-title and master-volume settings are gone, and so is the overlay: Dear ImGui, its fetch and patch, the
renderer's overlay command buffers and the game-font reader were removed (`runtime/ui/menu.c` only applies the
Fullscreen row's request on the window thread).

**2026-11-20**: the port's three Graphics rows come first on that page; Change Controllers is gone (Controls in its
row); the pause menu's Leaderboards row (online only) is **Save and Return to Title** and Save and Quit closes the game
after saving, both asking first ("Are you sure? Press A again" in the description box, with the game's select
sound); the Options screen is the same one in the pause menu (owner, checked). **2026-11-21**: the title screen has an
**Exit** button (the owner's icon, `packaging/art/exit-button.png`) left of the gear, in the game's own button frame;
left / right go Exit - gear - main column; A on it plays the game's select and quit sounds and closes the game. The
eShop button is gone (our button took its object).

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
- **Button row** (the main list's): constructor `(row (0x60 bytes), label id, desc id, std::function<void()> *, 0,
  0)`. The function is the game's bound member function with an int, heap-held (0x28 bytes: vtable, function, adjust,
  object, int). The main list binds the screen's "open page <int>" this way; through its own GOT slot we do the same
  for our page.
- **Pages**: a new row vector appended to the screen's page list is a working page. The game's open-page code selects
  its first row. Back returns to main row = page number (except page 1), so the Controls button sits at main row 5,
  the page's number.
- **Per-frame calls**: layout calls each row's "set y" (vtable +0x20) every frame; the selected row's input method
  (+0x18) runs every frame too. The hooks use these to refresh rows (F11, bindings) and to see A on a binding row.
- **Scrolling**: pages of more than 10 rows show 9 at a time, following the selection; the rest get y = 1000 (off the
  screen).
- Labels need the text lookup hook. The row's draw code calls the lookup by id, and an unknown id aborts in the
  game's text formatting.

## Pause menu and title screen (1.4.0; facts only)

- **Pause menu** screen object: its rows are text elements in fixed fields (+0x50 Return, +0x58 Options, +0x68
  Achievements, +0x60 Leaderboards, +0x70 Save and Quit; label ids 5, 46, 230, 103, 6), the selected row an index at
  +0x104 (0..4 those rows, 5 and 6 the Inventory and Map tabs), +0x118 set while the leaderboard kinds are shown, the
  description box at +0x48 (set with `0x700024c4c0 (box, text id)`). Per-frame update `0x700006aaa0`, description
  for the selected row `0x700006a9a0` (called on a change only). Save and Quit asks nothing, commits the save twice and
  goes to the title.
- Our hooks: the update (A on rows 3 and 4: first press asks, second runs the game's Save and Quit with the index set
  to 4; for Quit, `runtime/ui/menu.c` closes the window once a save was committed after the request and save writes
  stopped for 1.5 s, at most 20 s), the description, and the text lookup (id 103 -> our label).
- The menu select sound: `0x7000001710 (const std::string *name, 0, 0, std::string *out, d0..d5 = 1, 0, 0, 1, 0, 0)`;
  the name is read at run time from the game's data (`0x70008cab9f`), never written in the repository.
- **Options Back**: the game sets the selected main row to the page number it leaves (page 1: row 0) and calls
  "open page" `0x70000650f0 (screen, 0)`, which also moves the cursor; our hook there selects the Controls row instead
  when leaving our page.
- **Title screen** builder `0x7000056530`: the gear is a sprite (`0x700022f170 (sprite (0x1b0 bytes), const
  std::string *texture name)`) in an icon-button element (`0x700024b940 (element (0x80), sprite, 0x1d60, 0x1e)`) at
  screen +0x88. Its texture is a 32x32 RGBA8 BNTX in `textures_bin/texture_pack.bin` (one zlib stream, entries listed
  in `textures.xml`), drawn at the game's pixel scale: the visible art covers x 6..26, y 5..27, white with a one-pixel
  dark shadow, inside a frame the game draws.
- **Title layout** `0x70000551c0` (per frame): elements are placed with their vtable +0x10 `(element, x, y, width)`,
  and placing one draws it that frame; the buttons only while the title screen is on top (`0x700000d070 (screen)`).
  The gear at (20, 306, 31), the eShop button at (60, 306, 120) only when the byte behind GOT slot `0x7000a34a90` is
  set (an eShop mode, read in ~20 places; it also makes the gear open Options directly): off in this port.
- **Title update** `0x7000053ff0`: column at +0xc0 (0 gear, 1 eShop, 2 main), main row at +0xbc, input taken while
  i32 +0x14c <= 0; actions through `0x700040ebd0 (action, -1, 0)` (left 0x50 / 0x5c, right 0x4f / 0x5e, A 0x28 / 0x0e);
  left / right skip column 1 when the eShop mode is off; the selected column's button is highlighted (1: +0x90).
- **Textures by name**: a sprite asks a cache; on a miss `0x700022cc20` -> `0x70004046f0` loads the name from the
  packs, or else the loose file `data:/textures_bin/<name without .png>.bntx` (the game logs a warning that it was
  loaded outside a preload block). The port adds `textures_bin/gui/HM_ExitButton.bntx` to the RomFS image from memory
  (`romfs_layout_ex`), written by `runtime/hle/bntx.c` (32x32 RGBA8, our own writer; checked locally to give the
  game's gear file byte for byte from the gear's pixels and name).
- Our hooks: the title builder (makes a sprite with that texture and an icon button, `0x700024b940`, in the eShop
  field +0x90, deleting the eShop button), the layout (the gear and our button swap fields while the game lays out,
  so it draws ours at the gear's place; we draw the gear at (56, 306)), the update (left from the gear stops on ours,
  right from ours goes to the gear, A on ours quits: `runtime/ui/menu.c`, 0.4 s later for the sound).

- **Update button** (2026-11-21): column 3 of the title update (the game moves 3 -> 2 on left, ignores right, and
  highlights the gear (+0x88) for any column it doesn't know; our hook sets 0 <-> 3 <-> 2 and the highlight,
  `0x700024aaa0 (button, selected, 0 | -1)`, which the title calls on every button every frame). The icon button
  keeps its sprite at +0x78 and draws it each frame at its middle (`0x700024baf0`), with the frame the sprite holds
  (i32 sprite +0x68; the draw `0x700022f7e0` reads it when called with frame -1), the pivot the button set in its
  constructor (doubles +0x1a0 / +0x1a8, 0.5) and an offset it rewrites each frame (+0x188). A sprite's scale
  (`0x700022e390`, doubles +0x108 / +0x110) works from its top left while the pivot counts in unscaled sizes: a
  scaled sprite is centred with the pivot at half the scale. `0x700022f2a0 (sprite, name, frames, -1)` makes a sprite
  of a horizontal sheet; the vector at +0x170 and the frame index at +0x12c are for animations made of separate
  textures (indexing it with a sheet's frame crashed). The title fades its icon buttons in with `0x700024aae0
  (button, d0 = screen +0x198)` each frame.

## Plan (owner's decisions, 2026-11-19)

Rows go by topic, beside the game's own.

| Overlay setting | Decision | Work |
|---|---|---|
| Fullscreen | Yes/No row, Graphics | done, follows F11 / Alt+Enter |
| Scaling filter (4 choices, next start) | four-way row, Graphics | done (the game's choice row type; Pixel-perfect added 2026-11-20) |
| FPS in the window title | removed | done (old ini lines are ignored) |
| Frame pacing | Yes/No row, Graphics | done |
| Master volume | removed | done (old ini lines are ignored; `HM_AUDIO_GAIN` stays for tests) |
| Rebinding (16 buttons, keyboard and gamepad, reset) | new Controls page | done: a main-list button opens our page; one choice row per Switch button (its single choice is the bindings text, made at lookup time); A (or left/right) starts a capture in `input.c`, the next key or gamepad button binds that side, Esc / Home cancel; Reset row; the page scrolls (9 rows shown) |
| About (version, folder, keys) | version on the title screen | done 2026-11-21: game version + DLC and the port's version, bottom right |
| F1 / Minus+Plus | freed | done (the overlay is gone) |

Also:
- Our text in all 11 of the game's languages (en, ja, de, fr, cafr, es, uses, it, kr, sc, tc): done for the rows so
  far, drafted by the agent; a native check is wanted. New rows add their text to the table in `game_menu.c`
  (`tests/test_recomp.py` checks every text has every language).
- **Open**: check the pause menu's Options (same builder or another one?). Parked by the owner.
- **Done (2026-11-21)**: the version on the title screen. The game's "v1.4.0" is a text element (`0x7000232df0
  (text (0xf8), 1, 1, 0, 1)`) the title screen's constructor `0x7000053270` builds at screen +0x98 from the string
  `0x7000544ef0` returns (x8: a `std::string`, "v" + the version), converted to UTF-32 and set with `0x7000232f60
  (text, const std::u32string *, 0, const std::string *language)`. The title layout places it with `0x70002337c0
  (text, d0 = x, d1 = y)` at the doubles behind `0x700089e818` / `0x700089dbd8` (625, 315: its right end), only
  while the screen is on top. Our layout hook swaps +0x98 for our own element of the same class (the port's
  version) while the game lays out, then draws the game's element (text replaced: "Game Version: ... + DLC ...")
  14 units up and the update notice 28 up. (It had not been found by searching: it is no `localization.xml` text,
  no "1.4.0" string or immediate in `main`, and doesn't go through the text lookup's UTF-8 conversion.)
- Dear ImGui is gone: done.
- Addresses stay in the repository (open question 10, answered).

## Reproducing

```bash
python3 recomp/gen.py main ~/.cache/hylian-melodies/dev/exefs/main 0x7000000000 ~/.cache/hylian-melodies/gen-igg/main
python3 tools/build_game.py --gen ~/.cache/hylian-melodies/gen-igg --out ~/.cache/hylian-melodies/build-igg --target game
```

Then run from the title screen: gear (`left`, `a`) -> Options (`a`) -> two `down` -> Graphics (`a`) -> seven `down`.
In a test run: `HM_INPUT_SCRIPT=1700:left,1760:a,1960:a,2200:down,2300:down,2400:a,2600:down,...` with
`HM_RUN_SECONDS=80` (startup speed varies; leave margin). Menus need about 50 frames between presses.
