# Changelog

What changed for players in each release, newest first. Nothing of the game is in this repository or its releases:
the installer builds the game from your own cartridge dump and keys.

## 0.4.0 (2026-11-21)

Title screen
- The bottom right shows what is running: the game's version and DLC packs, and the Hylian Melodies version.
- **Update notice**: at start the game asks GitHub whether a newer Hylian Melodies is out and, if so, says
  "Update Available" above those lines. Nothing about you is sent. Off unless you turn it on: the installer asks
  (recommended), and Options > Gameplay > Check for updates switches it any time.
- **Update button**: while an update is available, an activated Sheikah Stone appears right of the gear. Choosing it
  closes the game and opens your terminal with the installer, which offers to build the new version from the same
  files as last time. In the Steam Deck's Gaming Mode it asks first, then switches to Desktop Mode, where the
  installer opens by itself.

Other
- The game window has the same icon as the menu entry.
- Started without a display or without a Vulkan driver, the game now says so plainly (and what to do) instead of
  crashing.

## 0.3.0 (2026-11-21)

Picture
- **Fixed on the Steam Deck and other integrated GPUs: squashed pixel art.** The game's 1280x720 image was drawn at
  853x480 there and scaled back up, losing rows and columns of pixels. It is now drawn at the game's own size on
  every GPU. On the Deck's 1280x800 screen the picture shows at exactly 1:1, with thin bars above and below (each
  screen of the game is made for 16:9, so it is not stretched).
- New Scaling filter choice, **Pixel-perfect**: the picture grows only in whole steps (2x, 3x, ...) with black
  borders, so every pixel is a perfect square. Sharp stays the default (at 1080p it fills more of the screen).
  Switching between Sharp and Pixel-perfect applies at once.

Menus
- Options: **Controls** takes the place of Change Controllers (no use on a PC). The port's Fullscreen, Frame pacing
  and Scaling filter rows now come first on the Graphics page.
- Pause menu: Leaderboards (online only) is now **Save and Return to Title**, and **Save and Quit** saves and closes
  the game. Both ask first: press A again to go ahead, or move away to cancel.
- Title screen: a new **Exit** button left of the gear closes the game. The eShop button is gone.
- The new texts are in all 11 of the game's languages (the translations are ours; corrections welcome).

## 0.2.0 (2026-11-20)

- The port's settings are now in the game's own Options menu: Fullscreen, Frame pacing and Scaling filter on the
  Graphics page, and a new Controls page to rebind every Switch button to a key or gamepad button, in all 11 of the
  game's languages.
- The F1 overlay menu is gone, along with the FPS-in-title and master-volume settings (the game's own Sound and
  Music volumes stay).

## 0.1.2 (2026-11-20)

- New output: a generic AppImage, one file that runs on any current x86-64 Linux (glibc 2.36 or newer), built in a
  container (podman or Docker).
- Immutable systems (SteamOS, Bazzite, Fedora Silverblue/Kinoite, openSUSE Aeon/Kalpa, ...) are detected and get the
  AppImage; the installer can put it in `~/Applications` with a menu entry.
- The launcher makes sure the game always uses your own player folder.

## 0.1.1 (2026-11-20)

- The installer is the one install route (it builds the pacman package too).
- Installer settings go into the game's own settings file.
- Packages name this repository as their homepage and state the licence.

## 0.1.0 (2026-11-17)

- First test release: the installer and the native Linux port, playable from the title screen through the game.
