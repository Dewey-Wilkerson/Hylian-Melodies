// The port's own update check (docs/DECISIONS.md, 2026-11-21): at start, on a background thread, ask the project's
// GitHub releases for the latest version and compare it with this build's. Host code only: the game's own network
// stays offline (services/net.c). Only with check_updates = 1 in hylian-melodies.ini (the installer asks; default
// off) or the Options row.
#pragma once
#include <stdbool.h>
#include <stddef.h>

void update_check_start(void);         // starts the check once, when the setting is on (later calls do nothing)
const char *update_check_newer(void);  // the newer version ("0.3.1") once the check found one, else NULL

// The title screen's update button (owner): the game closes, and the last thing it does is start the player's
// default terminal running the latest release's install.sh (README's curl line; the installer finds the last build
// in its manifest and offers to build it again). That window is on its own and outlives the game. With no terminal,
// the releases page opens in the browser.
enum { UPDATE_RAN_NOTHING, UPDATE_RAN_TERMINAL, UPDATE_RAN_BROWSER };
bool update_installer_available(void);    // a terminal (or xdg-open) to start: checked before the game closes
void update_run_installer_at_exit(void);  // at exit (atexit, after the window closed and the GPU work was saved)
int update_run_installer(void);           // now (what the exit runs; tests) -> what was started

// Gaming Mode (a gamescope session: SteamOS, Bazzite ...) shows no other program's window and the installer needs a
// keyboard, so there the button asks first and then switches to Desktop Mode (owner): a one-shot autostart entry
// starts the installer when the desktop comes up (it removes itself), and at exit the game runs
// steamos-session-select plasma, what Steam's own "Switch to Desktop" runs.
bool update_gaming_mode(void);
bool update_desktop_switch_available(void);  // steamos-session-select is there
bool update_switch_to_desktop_at_exit(void); // writes the autostart entry, switches at exit -> false if it can't

// (pure helpers, tests/c/test_update_check.c)
bool update_version_parse(const char *s, int v[3]);  // "v0.3.1", "0.3" -> {0,3,1}, {0,3,0}; false if not a version
bool update_version_newer(const char *a, const char *b);  // a > b (both parse)
bool update_tag_from_json(const char *json, char *out, size_t cap);  // the release's "tag_name"
