from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import ItemClassification, Location, LocationProgressType, Region
from rule_builder.options import OptionFilter
from rule_builder.rules import Has, HasAll, HasFromList, Rule, True_
from rule_builder.field_resolvers import FromOption, FromWorldAttr

from . import data, uncharted
from .data import Region as R
from .items import MassEffectLE1Item
from .options import MakoShuffled, RequiredSquadSize

if TYPE_CHECKING:
    from .world import MassEffectLE1World


class MassEffectLE1Location(Location):
    game = data.GAME_NAME


HAS_SQUAD: Rule = HasFromList(*data.SQUAD, count=FromOption(RequiredSquadSize))
HAS_MAKO: Rule = Has(data.MAKO) | OptionFilter(MakoShuffled, False)
HAS_FRAGMENTS: Rule = Has(data.FRAGMENT, count=FromWorldAttr("fragments_required"))
VIRMIRE_PAIR: Rule = HasAll("Kaidan Alenko", "Ashley Williams")  # D4: the bomb choice needs both


def _mission(world_region: R) -> Rule:
    """Galaxy-map access to a mission world: its coordinates, a squad, and the Mako."""
    return Has(data.COORDINATES[world_region]) & HAS_SQUAD & HAS_MAKO


ENTRANCES: dict[R, Rule] = {
    R.CITADEL: True_(),  # D3: Act 1 starts on first landing
    R.EDEN_PRIME: Has(data.COORDINATES[R.EDEN_PRIME]),  # tutorial world, assumed solo-able (R2/R4)
    R.THERUM: _mission(R.THERUM),
    R.FEROS: _mission(R.FEROS),
    R.NOVERIA: _mission(R.NOVERIA),
    R.VIRMIRE: _mission(R.VIRMIRE) & VIRMIRE_PAIR,
    R.ASTEROID_X57: _mission(R.ASTEROID_X57),
    R.ILOS: HAS_FRAGMENTS & Has(data.EVENT_VIRMIRE) & HAS_SQUAD & HAS_MAKO,  # D5, D9
    R.UNCHARTED: Has(data.EVENT_ACT1) & HAS_MAKO,  # owner decision 2026-10-10: uncharted content after Act 1
}


def location_included(world: MassEffectLE1World, loc: data.LocationData) -> bool:
    """Whether this seed has the location: its region exists and its codexsanity tier is on."""
    if loc.region is R.ASTEROID_X57 and not world.options.bring_down_the_sky:
        return False
    if loc.codex is not None:
        level = world.options.codexsanity.value
        return level == 2 or (level == 1 and loc.codex == "story")
    if loc.journal is not None:
        level = world.options.journalsanity.value
        return level == 2 or (level == 1 and loc.journal == "story")
    if loc.shop_slot is not None:
        return loc.shop_slot < world.options.shop_slots.value
    if loc.locked and not world.options.unlock_containers:
        return False
    if loc.container == "station":
        return bool(world.options.aid_stations)
    if loc.container == "container":
        return world.options.containersanity.value >= 1
    if loc.container == "drop":
        return world.options.containersanity.value == 2
    return True


# Therum and Virmire close once finished (GateOverride F1402/F699; their levels never check the done bools, so reopening
# would replay the mission). Codex pages set only inside the Virmire mission (research/le1_codex_uses.tsv).
CLOSING_MISSIONS = (R.THERUM, R.VIRMIRE)
MISSION_ONLY_CODEX = frozenset({
    "Codex: Aliens: Council Races: Salarians: Culture",
    "Codex: Aliens: Council Races: Salarians: Government",
    "Codex: Aliens: Council Races: Salarians: Military Doctrine",
})


def location_excluded(world: MassEffectLE1World, name: str, loc: data.LocationData) -> bool:
    """Filler only: a story choice can skip it, its planet's landing condition is unverified, or it is left behind
    for good when its mission ends (finished_mission_checks: filler_only)."""
    if loc.excluded or uncharted.location_unverified(name):
        return True
    return (world.options.finished_mission_checks == world.options.finished_mission_checks.option_filler_only
            and loc.region in CLOSING_MISSIONS
            and (loc.container is not None or loc.shop_slot is not None or name in MISSION_ONLY_CODEX))


def create_regions(world: MassEffectLE1World) -> None:
    regions = {r: Region(r.value, world.player, world.multiworld) for r in R}
    if not world.options.bring_down_the_sky:
        del regions[R.ASTEROID_X57]
    world.multiworld.regions += regions.values()

    normandy = regions[R.NORMANDY]
    for target, rule in ENTRANCES.items():
        if target in regions:
            world.create_entrance(normandy, regions[target], rule, name=f"Galaxy Map -> {target.value}")
    regions[R.ILOS].connect(regions[R.FINAL_CITADEL], "Ilos -> Conduit")  # linear story

    for name, loc in data.LOCATIONS.items():
        if not location_included(world, loc):
            continue
        location = MassEffectLE1Location(world.player, name, data.LOCATION_NAME_TO_ID[name], regions[loc.region])
        if location_excluded(world, name, loc):
            location.progress_type = LocationProgressType.EXCLUDED
        regions[loc.region].locations.append(location)

    _add_event(world, regions[R.CITADEL], data.EVENT_ACT1)
    if world.options.human_squad_at_citadel:
        # Same names as the items, so HAS_SQUAD and VIRMIRE_PAIR count them; no ID, so the client never sets InParty.
        for name in data.HUMAN_SQUAD:
            _add_event(world, regions[R.CITADEL], name, f"Citadel: {name} Joins (arrival)")
    _add_event(world, regions[R.FEROS], data.EVENT_FEROS)
    _add_event(world, regions[R.NOVERIA], data.EVENT_NOVERIA)
    _add_event(world, regions[R.VIRMIRE], data.EVENT_VIRMIRE)
    _add_event(world, regions[R.FINAL_CITADEL], data.EVENT_VICTORY)


def _add_event(world: MassEffectLE1World, region: Region, name: str, location_name: str | None = None) -> None:
    location = MassEffectLE1Location(world.player, location_name or name, None, region)
    location.place_locked_item(MassEffectLE1Item(name, ItemClassification.progression, None, world.player))
    region.locations.append(location)
