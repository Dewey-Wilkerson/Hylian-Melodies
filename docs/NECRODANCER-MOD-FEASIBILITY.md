# Side study: Cadence of Hyrule as a Crypt of the NecroDancer mod?

Date: 2026-11-13. Scope: about an hour of desk research, no implementation, nothing downloaded. Question: instead of
statically recompiling the Switch game (this repo's route), could *Cadence of Hyrule* (CoH) be delivered as a mod for
the PC *Crypt of the NecroDancer* (CotND) with the Synchrony mod framework?

Confidence labels: **high** = stated by a primary source or by this repo's own recon; **medium** = strongly implied by
sources, not stated outright; **low** = my inference or memory, not verified this session.

Local check: CotND (Steam app 247080) is **not installed** on this machine (no app manifest or `common/` folder in
the only Steam library, `~/.local/share/Steam`). So no version or Synchrony presence to report, and nothing below was
tested against the real game.

---

## 1. NecroDancer's modding surface today

- **Synchrony** is a paid DLC for CotND (Early Access Aug 2022, full release 13 Mar 2024 on PC/Mac/Linux, PS4,
  Switch). It is a reimplementation of the game in C++ with Lua scripting, and brings online multiplayer, a mod
  framework and an in-game mod portal. (high: [Gematsu 2024][gematsu24], [GamingOnLinux 2022][gol22],
  [TCRF Synchrony page][tcrf], the last one not reachable this session; quoted from a search snippet)
- **Language:** Lua on LuaJIT 2.1 (Lua 5.1 compatible). Mods hook into an event system (handlers with ordering keys,
  overriding other handlers allowed "as a last resort") and a custom entity-component system in which an entity's
  components are fixed at creation. Gameplay must be fully deterministic for multiplayer. (high for Lua/LuaJIT and
  ECS, from [Synchrony docs overview][sdocs-ov]; sandboxing rules not stated anywhere I read)
- **What the API exposes (module names in the official docs index, [vortexbuffer docs][sdocs]):** common enemies,
  items, weapons, spells, traps, shrines; playable characters; procedural level generation *and* an XML dungeon loader
  and dungeon files (custom hand-made levels, distributable via the workshop); custom music with playlists and custom
  beatmaps; soundtrack definitions; cutscene definitions and renderer; subtitles; text pools; HUD, HUD layout, beat
  bar, inventory HUD, minimap themes; camera and camera targets; game-mode modifiers (rhythm mode, hard mode, etc.).
  (high that these modules exist; **medium/low** on how far each can be pushed, because the pages are function
  indexes with little prose)
- **Known limits:**
  - API declared work-in-progress and subject to change ([legacy API manual][sdocs-legacy]). (high)
  - Beatmaps are tied to songs; the beat logic runs client-side. Music/beatmap formats accepted for custom songs are
    not stated in the docs I read. (medium)
  - Everything is a single grid/tilemap dungeon floor at a time, entered and left through stairs, with the
    camera following the player(s) over that floor. Nothing in the docs suggests a seamless or screen-by-screen
    overworld. (medium: inferred from the API shape and the game's design, not from a stated limit)
  - No native code in mods (Lua only). (medium: implied, not stated)
- **Distribution:** in-game mod portal backed by **mod.io** ([mod.io/g/crypt][modio]) and **Steam Workshop**
  modules. Mods by a Synchrony developer have been published on mod.io (e.g. *Drift of the NecroDancer*, 2026,
  [Game*Spark][gamespark]). (high) Content rules: mod.io and Steam both forbid uploading material you do not hold
  rights to (general terms of both services; low as to any CotND-specific rule, none found). For this project that
  is moot: nothing Nintendo- or CoH-derived could be uploaded anyway, so a mod would be personal-use, installed
  locally, with its assets generated on the user's machine (see section 3).
- **Prior art:** music-swap mods that remap CotND zones to CoH-style tracks exist on the Workshop (they need the
  user's own soundtrack), and a Workshop item described as a "fan sequel" to CoH (*Hylian Resurgence*, alpha 1.2,
  2023-24) exists, contents unverified ([mirror listing][hr]). (low/medium) Neither is an attempt to run CoH's own
  content.

## 2. How different CoH's gameplay is

| CoH feature | Expressible in Synchrony? | Confidence |
|---|---|---|
| Grid movement on the beat, weapons, enemy move patterns | Yes, this is the core shared design | high |
| "Fixed beat" mode (enemies move on the beat, player moves freely) | Probably, as a rule modifier over the beat system; the docs show modifier modules but no example | low |
| Large overworld made of connected screens, randomised layout per save, walking off one screen edge into the next, screen-locked camera | **Not native.** CotND is floor-by-floor with stairs. A mod would have to fake screens as separate floors or one huge floor with a scripted camera; seamless transitions, persistent per-screen state (killed enemies, opened chests, burnt bushes) across the whole map would be new systems in Lua | medium |
| Dungeons with keys, locked doors, puzzles, boss rooms | Partly: CotND has floors, locked doors, bosses; Zelda-style key logic and puzzle switches would be new Lua | medium |
| Persistent inventory, equipment that survives death, rupees/diamonds economy, shops, upgrades, heart containers, stamina-like systems | Partly: items and shops exist, but CotND's run-based "lose your items at death" loop is the opposite of CoH's persistent progression; save/progression would be custom | medium |
| Multiple characters switched at waypoints, character-specific abilities | Playable characters yes; switching mid-game at waypoints would be custom | medium |
| Story, NPC dialogue, cutscenes, map screen, quest flags | Cutscene/subtitle/text modules exist; a full NPC/quest/flag system and map screen do not appear in the API and would be written from scratch | low/medium |
| Bosses with multi-phase, music-synchronised patterns | Bosses exist; each CoH boss would be re-scripted by hand | medium |
| Adaptive music that layers instruments by nearby enemies, per-area themes | CotND has a shopkeeper/zone track system; CoH's FMOD-driven adaptive mixing (see section 3) would need either FMOD Studio event playback (not exposed as far as I can tell) or pre-rendered stems mixed in Lua | low |
| Local co-op | Synchrony has co-op; CoH's co-op rules would be re-scripted | medium |

Bottom line: the beat-grid core is shared, but most of what makes CoH *CoH* (overworld, persistence, story,
character switching, adaptive music) is not in CotND and would be new game logic written in Lua against a work-in-
progress API.

## 3. Asset side

CoH's data, from `docs/RECON.md` sections 3-4 (generic): ~560 XML level/game data files, 40 FMOD Studio banks
(1.1 GiB), 32 music-related text files, 14 H.264/AAC MP4 videos, 14 zlib-compressed binary files, 8 NVN shader
binaries (BNSH), 6 BFFNT fonts, 5 BNTX textures, 4 colour lookup tables. The game's sprites are therefore
mostly inside the few BNTX containers (atlases), and the game logic lives in native ARM64 code, not in data.

What CotND/Synchrony consumes: PNG sprite sheets, OGG music with beat files for custom songs, XML dungeon files,
Lua for logic. (medium: OGG music for the classic game per a [Steam thread][ogg]; Synchrony's exact custom-music
format not stated in docs read.) Whether Synchrony still uses FMOD: **unknown** (low; the original game is widely
said to use FMOD for music speed changes, not verified this session). It does not matter much: CoH's FMOD *Studio*
banks hold events, parameters and adaptive-mix logic that CotND's music path would not interpret even if it linked
FMOD.

An install-time converter (same legal model as this repo: run on the user's own dump, write to
`~/.local/share/...`, ship nothing) is conceivable. Needed pieces and open tools:

| Conversion | Tool candidates | License | Notes |
|---|---|---|---|
| RomFS extraction | hactool via `installer/hactool.py` (already in this repo) | ISC | done |
| BNTX -> PNG (Tegra block-linear deswizzle + BCn/ASTC decode) | `tegra_swizzle` (Rust, [docs.rs][tswz]); Switch Toolbox ([GitHub][stb]); BnTxx ([GitHub][bntxx]) | tegra_swizzle: MIT (low, from memory; repo LICENSE not read); Switch Toolbox: **GPL-3.0** (excluded by AGENTS.md rule 5); BnTxx: not stated | own small decoder over tegra_swizzle + a BCn decoder is realistic |
| Sprite atlas -> CotND sprite sheets (cut, re-layout, frame timing) | none; needs CoH's atlas metadata from its XML/binary data | n/a | custom, per sprite, large manual effort |
| FMOD Studio `.bank` -> FSB5 -> OGG/WAV | python-fsb5 ([GitHub][pyfsb5], MIT); Fmod5Sharp ([GitHub][f5s], MIT); fsbex (Rust, [GitHub][fsbex], MIT/Apache-2.0); FModBankParser ([NuGet][fbp], Apache-2.0); vgmstream ([fork mirror][vgm], ISC-style per my memory, low) | permissive | extracts *samples*; Studio event/parameter/mix logic is lost, so adaptive music must be re-built |
| Beat maps for each track | CoH's music text files may carry tempo/beat data (generic count only, format not checked); else derive from BPM | n/a | custom |
| XML level data -> CotND dungeon XML | none; schema mapping unknown | n/a | CoH levels are screen templates for a randomised overworld, not CotND floors (medium) |
| BFFNT fonts -> PNG bitmap font | Switch Toolbox (GPL-3.0) or own parser | n/a | small |
| MP4 cutscenes | play as-is through whatever Synchrony offers, or skip; FFmpeg is LGPL/GPL (approval needed) | | Synchrony has no documented video playback (low) |
| BNSH shaders | not applicable: effects would be redone in CotND's renderer | | |

Legally the converter model holds the same way as this repo's (nothing shipped), but every CoH *behaviour* would be
hand-written, so the Lua code itself would be a clean-room re-implementation of game rules: allowed under the repo
rules as long as no strings, tables or bytes are copied in, yet hard to keep clean when the reference for every
number is the game's own data.

## 4. Effort, risk and fidelity vs. recompilation

| | Recompilation (this repo) | Synchrony mod |
|---|---|---|
| Done so far | M0-M3 done; M4 boots headless through SDK init, constructors, RomFS mount, vi layer; stops at NVN (`docs/PROGRESS.md`) | nothing |
| What remains | NVN-on-Vulkan (LAS Recomp's layer exists in history), shaders, audio out, input, saves, DLC, packaging: large but **bounded, generic** work with two working reference ports | design and write every CoH system in Lua (overworld, screens, persistence, inventory, NPCs, quests, bosses, characters, adaptive music), asset converters, beat maps: **unbounded, content-specific** work |
| Order of magnitude (low confidence) | months for one person with references | a fan-game-scale project, likely a year or more of game design and scripting, plus art/audio re-layout |
| Main risks | NVN/Maxwell shader translation, timing/audio latency, game-specific traps | API churn (WIP API), CotND's floor-based design fighting an overworld, adaptive music without FMOD Studio events, never reaching "feature complete" |
| Fidelity | runs CoH's own code and data: behaviour, RNG, balance, bugs and DLC identical by construction | a re-implementation: enemy patterns, damage numbers, RNG, overworld generation, boss AI, music mixing would all be approximations unless each is reverse-engineered from the binary, which is the very work the recompiler avoids |
| Needs | the user's dump + keys | the user's dump + keys **and** CotND + Synchrony DLC (paid, not installed here) |
| Extras | — | online multiplayer, Synchrony's mod ecosystem |

Fidelity in plain words: a mod would be "a NecroDancer game that looks and sounds like CoH", not CoH. Even with
perfect asset conversion, every rule a player notices (how an enemy moves, when the overworld reshuffles, how much a
heart heals, what the fixed-beat mode tolerates) would be guessed or painstakingly re-derived. The recompiled port
gets all of that for free once the platform layer works.

## 5. Recommendation

**Not worth switching; not worth it as a side project either, at least until the port plays.** (confidence:
medium-high)

- The recompilation route already has the hard, risky platform-independent part behind it (lift, link, boot to
  graphics init) and the remaining work is generic platform work with reference implementations. A mod restarts
  from zero on the far larger and open-ended job of rewriting the game's logic.
- Synchrony is built around run-based dungeon floors; CoH's overworld, persistence and story are exactly the parts it
  lacks, so the mod would spend most effort fighting the host game.
- The result would be less faithful than the port by construction and would add a second paid dependency.
- The one thing a mod offers that the port does not is online co-op and a modding ecosystem. If that becomes
  wanted later, the cheaper path is to add features on top of the working port, or to make a small, explicitly
  "inspired-by" Synchrony mod (a fixed-beat modifier, a CoH-style music remap from the user's own banks) as a
  weekend toy, not as the delivery vehicle.

Open question worth one line (not researched): CoH (2019) and Synchrony (2022) are both C++ engines by the same
studio lineage; whether they share code or data formats (e.g. the XML schemas) is unknown and would change the
asset-mapping cost, but not the logic-rewrite cost.

---

### Sources

[gematsu24]: https://www.gematsu.com/2024/03/crypt-of-the-necrodancer-dlc-synchrony-now-available-for-ps4-switch-and-pc
[gol22]: https://www.gamingonlinux.com/2022/08/crypt-of-the-necrodancer-synchrony-dlc-released-into-early-access/page=1/
[tcrf]: https://new.tcrf.net/Crypt_of_the_NecroDancer/Synchrony
[sdocs]: https://vortexbuffer.com/synchrony/docs/
[sdocs-ov]: https://vortexbuffer.com/synchrony/docs/overview/
[sdocs-legacy]: https://marukyu.github.io/synchrony-api-legacy/manual/00-readme.md.html
[modio]: https://mod.io/g/crypt
[gamespark]: https://www.gamespark.jp/article/2026/04/02/164705.html
[hr]: https://catalogue.smods.ru/archives/72781
[ogg]: https://steamcommunity.com/app/247080/discussions/0/2217311444321061821
[tswz]: https://docs.rs/tegra_swizzle
[stb]: https://github.com/MichaelHinrichs/Switch-Toolbox
[bntxx]: https://github.com/gdkchan/BnTxx
[pyfsb5]: https://github.com/HearthSim/python-fsb5
[f5s]: https://github.com/SamboyCoding/Fmod5Sharp
[fsbex]: https://github.com/astral4/fsbex
[fbp]: https://packages.nuget.org/packages/FModBankParser/
[vgm]: https://github.com/rebolomo/vgmstream

- Synchrony release and features: [Gematsu 2024][gematsu24], [GamingOnLinux 2022][gol22], [TCRF][tcrf]
- Synchrony modding API: [docs index][sdocs], [overview][sdocs-ov], [legacy manual][sdocs-legacy]
- Distribution: [mod.io CotND][modio], [Game*Spark on a mod.io mod][gamespark]
- Prior art: [Hylian Resurgence listing mirror][hr]
- CotND music format: [Steam discussion][ogg]
- Converters: [tegra_swizzle][tswz], [Switch Toolbox][stb], [BnTxx][bntxx], [python-fsb5][pyfsb5],
  [Fmod5Sharp][f5s], [fsbex][fsbex], [FModBankParser][fbp], [vgmstream (fork)][vgm]
- This repo: `docs/RECON.md` sections 3-4, `docs/PROGRESS.md`
