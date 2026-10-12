# Archipelago for Mass Effect 1 (Legendary Edition)

An [Archipelago](https://archipelago.gg) multiworld randomizer for Mass Effect 1 in Mass Effect Legendary Edition.

**Status: beta test (0.2.3).** It's playable from start to finish on the Steam release (English). Expect rough edges.
Shop slots, the in-game tracker and the 0.2.3 additions (shop item names, F7 summary box, sprint fix) are not yet
confirmed in game.

## What changes

Shepard starts as a Spectre on the Normandy with no squad. Eden Prime, Therum, Feros, Noveria, Virmire and Asteroid X57
stay locked on the galaxy map until you find their coordinates. Squadmates, weapons, armor, bio-amps, omni-tools and
upgrades are all items. Ilos opens once Virmire is done and you've collected enough Prothean Beacon Fragments. You win
by defeating Saren and Sovereign on the Citadel.

Checks include story milestones, recruitments, Codex pages, journal entries, shop slots (entries at ten merchants that
show the item they hold, such as "Link's Hookshot"), and (optionally) containers and Aid Stations. Sent and received
items show as notices on the HUD, sprinting can be made infinite, and the galaxy-map travel videos are skipped.

**In-game tracker:** the client works out your seed's logic as you play. Press **F7** for a summary box (checks in logic
per region, every uncharted planet worth visiting, what each locked world still needs), check the **Archipelago** assignment in the journal (fragments,
coordinates, squad, checks in logic), and look for "Archipelago" callouts on the galaxy map. See the [game page](worlds/mass_effect_le1/docs/en_Mass%20Effect%20Legendary%20Edition%201.md) for the details.

## Download and install

1. Download `ArchipelagoME1-<version>.zip` from the [latest release](../../releases/latest) and unzip it.
2. Follow the [setup guide](worlds/mass_effect_le1/docs/setup_en.md). In short:
   - Archipelago **0.6.8 or newer**: double-click `mass_effect_le1.apworld`.
   - ME3Tweaks Mod Manager: import and apply `ArchipelagoME1-mod.zip`, and install the ASI loader.
   - Run `install-bridge.ps1` to install the game bridge.
   - Start a **new career**, then open **Mass Effect LE1 Client** from the Archipelago Launcher and connect before you
     open any shop.

Mass Effect 1 is a custom world: make your YAML in the Launcher's **Options Creator**, generate with **Generate** in
the Launcher, then host the seed on [archipelago.gg](https://archipelago.gg/uploads) (upload the generated zip) or with
**Host** in the Launcher.

The YAML template (`Mass Effect Legendary Edition 1.yaml`) is in the release zip.

## Reporting bugs

Open an [issue](../../issues) and include:

- What you did and what happened (the planet or mission, what you picked up or talked to).
- The newest `ME1Client_*.txt` from Archipelago's `logs` folder (for example `C:\ProgramData\Archipelago\logs`).
- Your YAML and the seed, if the problem is about logic (something unreachable, or reachable too early).

## Repository layout

- `worlds/mass_effect_le1/`: the Archipelago world (logic, items, locations, options) and the client.
- `tools/release/`: the release packaging script and the bridge installer.

The game mod and the bridge ship as built files in the release zip.
