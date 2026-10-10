# Mass Effect Legendary Edition 1 Setup Guide

Version 0.1 (alpha). Tested on the Steam release of Mass Effect Legendary Edition, English.

## Requirements

- Mass Effect Legendary Edition (Steam or EA app), Mass Effect 1 installed.
- [ME3Tweaks Mod Manager](https://me3tweaks.com/modmanager/) (installs the game mod and the ASI loader).
- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.8 or newer.
- The release archive: `mass_effect_le1.apworld`, `ArchipelagoME1-mod.zip`, the `ASI` folder and
  `install-bridge.ps1`.

## 1. Install the world

Double-click `mass_effect_le1.apworld` (or copy it into `Archipelago/custom_worlds`). The Archipelago Launcher then
lists **Mass Effect LE1 Client**.

## 2. Install the game mod

1. Open ME3Tweaks Mod Manager and select Mass Effect 1 (Legendary Edition).
2. Drag `ArchipelagoME1-mod.zip` onto Mod Manager (or *Mod Management > Import mod from archive*), then apply
   **Archipelago for Mass Effect 1**.
3. In *Tools > ASI Manager* (Mass Effect 1 LE), install **LE1 Autoload Enabler** and **LE1 AutoTOC** if they are not
   installed yet. This also installs the ASI loader.

## 3. Install the bridge

The bridge (`LE1APBridge.asi`) lets the client read and write the game's plot state and hand over items.

- Right-click `install-bridge.ps1` > *Run with PowerShell*. It finds the game in the usual Steam and EA folders; if it
  does not, run it from a PowerShell window with `-GamePath "<folder that contains Game\ME1>"`.
- Or copy both files from the `ASI` folder into `<Mass Effect Legendary Edition>\Game\ME1\Binaries\Win64\ASI\` by
  hand (delete any older `LE1APBridge*.asi` there).

## 4. Recommended

[Proper Convo-Cutscene Skipper](https://www.nexusmods.com/masseffectlegendaryedition/mods/1681) lets you skip
conversations and cutscenes. Install it through Mod Manager.

## 5. Play

1. Generate a seed with your YAML (template: `Mass Effect Legendary Edition 1.yaml`) and host it.
2. Start the game and start a **new career**. After character creation you are a Spectre on the Normandy.
3. Open the Archipelago Launcher > **Mass Effect LE1 Client** and connect with your slot name. The client says
   "Connected to LE1APBridge with a game world loaded" once a save is loaded.

The client must run on the same PC as the game. Checks you make while the client is closed are kept in your save and
sent the next time it connects; items you receive while the game is closed arrive when you load your save.

## Uninstall

In Mod Manager, *Restore* the game (or delete `BioGame\DLC\DLC_MOD_ArchipelagoME1`), then delete `LE1APBridge*.asi`
and `LE1APBridge.checks.tsv` from `Game\ME1\Binaries\Win64\ASI\`.
