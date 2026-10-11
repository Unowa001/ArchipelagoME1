"""In-game tracker: what is in logic right now, per area, and what each locked destination still needs.

The client rebuilds the seed's logic with the world's own regions and rules (a one-player MultiWorld built from slot
data), collects the items received so far, and evaluates every location the server still lists as missing. Options
that only decide whether a location exists are turned all the way up for the rebuild: the server's location list
decides that, so every location the seed can have also exists in the rebuilt world. The results go to the HUD (bridge
NOTE), later also to the journal and the galaxy map.
"""
from __future__ import annotations

import logging
from argparse import Namespace
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from BaseClasses import CollectionState, MultiWorld
from worlds.AutoWorld import call_single

from . import data
from .data import Region as R

# Options that only decide whether a location exists (or holds filler): turned up so the rebuild has every location.
INCLUSIVE_OPTIONS: dict[str, Any] = {
    "codexsanity": "full", "journalsanity": "full", "containersanity": "with_drops", "aid_stations": True,
    "unlock_containers": True, "shop_slots": data.SHOP_SLOTS_MAX,
}

# Level package prefix -> area shown on the HUD (story worlds; uncharted levels map to their planet below).
STORY_LEVELS: dict[str, str] = {
    "BIOA_NOR": R.NORMANDY.value, "BIOA_STA": R.CITADEL.value, "BIOA_PRO": R.EDEN_PRIME.value,
    "BIOA_LAV": R.THERUM.value, "BIOA_WAR": R.FEROS.value, "BIOA_ICE": R.NOVERIA.value, "BIOA_JUG": R.VIRMIRE.value,
    "BIOA_LOS": R.ILOS.value, "BIOA_CRD": R.FINAL_CITADEL.value, "BIOA_UNC52": R.ASTEROID_X57.value,
}
# Uncharted levels (research/le1_uncharted_maps.tsv): container checks are named after these planets.
UNCHARTED_LEVELS: dict[str, str] = {
    "BIOA_FRE31": "MSV Cornucopia", "BIOA_FRE32": "MSV Ontario", "BIOA_FRE33": "MSV Worthington",
    "BIOA_FRE34": "MSV Fedele", "BIOA_FRE35": "Unidentified Space Facility", "BIOA_UNC10": "Klensal",
    "BIOA_UNC11": "Xawin", "BIOA_UNC13": "Mavigon", "BIOA_UNC17": "Antibaar", "BIOA_UNC20": "Trebin",
    "BIOA_UNC21": "Rayingri", "BIOA_UNC24": "Altahe", "BIOA_UNC25": "Edolus", "BIOA_UNC30": "Chohe",
    "BIOA_UNC31": "Amaranthine", "BIOA_UNC42": "Nonuel", "BIOA_UNC51": "Luna", "BIOA_UNC53": "Agebinium",
    "BIOA_UNC54": "Presrop", "BIOA_UNC55": "Solcrum", "BIOA_UNC61": "Tuntau", "BIOA_UNC62": "Nepheron",
    "BIOA_UNC71": "Metgos", "BIOA_UNC73": "Nepmos", "BIOA_UNC80": "Nodacrux", "BIOA_UNC81": "Chasca",
    "BIOA_UNC82": "Ontarom", "BIOA_UNC83": "Casbin", "BIOA_UNC84": "Eletania", "BIOA_UNC90": "Sharjila",
    "BIOA_UNC92": "Binthu", "BIOA_UNC93": "Maji",
}
UNCHARTED_PLANETS = frozenset(UNCHARTED_LEVELS.values())
# Galaxy-map markers (le1mod markers, same order as tools/le1mod/Markers.cs Areas): area i shows "Archipelago: checks in
# logic" while bool MARKER_IN_LOGIC_BASE + i is set and "Archipelago: locked checks" while MARKER_LOCKED_BASE + i is.
MARKER_IN_LOGIC_BASE = 20850
MARKER_LOCKED_BASE = 20900
MARKER_AREAS: tuple[str, ...] = (
    R.CITADEL.value, R.EDEN_PRIME.value, R.THERUM.value, R.FEROS.value, R.NOVERIA.value, R.VIRMIRE.value,
    R.ASTEROID_X57.value, R.ILOS.value, *UNCHARTED_LEVELS.values(),
)
UNCHARTED_OTHER = "Uncharted (other)"  # uncharted codex/journal checks: not tied to one planet


def level_area(level: str) -> str | None:
    """HUD area of a level package name (e.g. BIOA_WAR20_03_DSG -> Feros), None for menus and unknown levels."""
    level = level.upper()
    for prefix, area in UNCHARTED_LEVELS.items():
        if level.startswith(prefix):
            return area
    for prefix, area in sorted(STORY_LEVELS.items(), key=lambda kv: -len(kv[0])):
        if level.startswith(prefix):
            return area
    return None


def location_area(name: str, loc: data.LocationData) -> str:
    """Story regions by region; uncharted checks by planet when the name says which (containers), else one bucket."""
    if loc.region is not R.UNCHARTED:
        return loc.region.value
    planet = name.split(":", 1)[0]
    return planet if planet in UNCHARTED_PLANETS else UNCHARTED_OTHER


def area_region(area: str) -> str:
    return R.UNCHARTED.value if area in UNCHARTED_PLANETS or area == UNCHARTED_OTHER else area


@dataclass
class AreaCount:
    in_logic: int = 0
    locked: int = 0


@dataclass
class TrackerStatus:
    areas: dict[str, AreaCount] = field(default_factory=dict)
    blockers: dict[str, list[str]] = field(default_factory=dict)  # destination region -> what it still needs
    fragments: int = 0
    fragments_required: int = 0
    ilos_open: bool = False

    def area(self, area: str) -> AreaCount:
        return self.areas.get(area, AreaCount())


class Tracker:
    def __init__(self, slot_data: Mapping[str, Any], player_name: str = "Shepard") -> None:
        from .world import MassEffectLE1World

        multiworld = MultiWorld(1)
        multiworld.game = {1: MassEffectLE1World.game}
        multiworld.player_name = {1: player_name}
        multiworld.set_seed(0)
        args = Namespace()
        for key, option in MassEffectLE1World.options_dataclass.type_hints.items():
            value = INCLUSIVE_OPTIONS.get(key, slot_data.get(key, option.default))
            setattr(args, key, {1: option.from_any(value)})
        multiworld.set_options(args)
        multiworld.state = CollectionState(multiworld)
        world_logger = logging.getLogger(MassEffectLE1World.__module__)  # generate_early's clamping warnings: not ours here
        disabled, world_logger.disabled = world_logger.disabled, True
        try:
            call_single(multiworld, "generate_early", 1)
        finally:
            world_logger.disabled = disabled
        self.world: MassEffectLE1World = multiworld.worlds[1]
        self.world.fragments_required = int(slot_data.get("fragments_required", self.world.fragments_required))
        call_single(multiworld, "create_regions", 1)
        call_single(multiworld, "set_rules", 1)
        self.multiworld = multiworld

    def state(self, received_item_ids: Iterable[int]) -> CollectionState:
        state = CollectionState(self.multiworld)
        for item_id in received_item_ids:
            name = self.world.item_id_to_name.get(item_id)
            if name is not None:
                state.collect(self.world.create_item(name), prevent_sweep=True)
        state.sweep_for_advancements()  # events (Act 1, Feros/Noveria/Virmire Complete, the human squad option)
        return state

    def status(self, received_item_ids: Iterable[int], missing_location_ids: Iterable[int]) -> TrackerStatus:
        received = list(received_item_ids)
        state = self.state(received)
        status = TrackerStatus(fragments_required=self.world.fragments_required)
        status.fragments = state.count(data.FRAGMENT, 1)
        pending_regions: set[str] = set()
        for location_id in missing_location_ids:
            name = self.world.location_id_to_name.get(location_id)
            if name is None or name not in data.LOCATIONS:
                continue
            try:
                location = self.multiworld.get_location(name, 1)
            except KeyError:
                continue
            count = status.areas.setdefault(location_area(name, data.LOCATIONS[name]), AreaCount())
            if location.can_reach(state):
                count.in_logic += 1
            else:
                count.locked += 1
            pending_regions.add(data.LOCATIONS[name].region.value)
        for region in pending_regions:
            if not self.multiworld.get_region(region, 1).can_reach(state):
                status.blockers[region] = self.blockers(region, state)
        status.ilos_open = self.multiworld.get_region(R.ILOS.value, 1).can_reach(state)
        return status

    def blockers(self, region: str, state: CollectionState) -> list[str]:
        """What the galaxy-map entrance to this region still needs, in short HUD words (mirrors regions.ENTRANCES)."""
        options = self.world.options
        has = lambda item: state.has(item, 1)  # noqa: E731
        needs: list[str] = []
        target = R(region)
        if target in (R.NORMANDY, R.CITADEL):
            return needs  # the start, and open from the start (D3)
        if target is R.FINAL_CITADEL:
            target = R.ILOS
        if target is R.UNCHARTED:
            if not has(data.EVENT_ACT1):
                needs.append("Act 1")
        elif target in data.COORDINATES and not has(data.COORDINATES[target]):
            needs.append("coords")
        if target is R.ILOS:
            fragments = state.count(data.FRAGMENT, 1)
            if fragments < self.world.fragments_required:
                needs.append(f"fragments {fragments}/{self.world.fragments_required}")
            if not has(data.EVENT_VIRMIRE):
                needs.append("finish Virmire")
        if target not in (R.EDEN_PRIME, R.UNCHARTED):
            # HasFromList counts copies (a start-inventory squadmate plus the pooled one count twice), as generation does.
            missing = options.required_squad_size.value - sum(state.count(name, 1) for name in data.SQUAD)
            if missing > 0:
                needs.append(f"{missing} squad")
        if target is R.VIRMIRE:
            pair = [name.split()[0] for name in ("Kaidan Alenko", "Ashley Williams") if not has(name)]
            if pair:
                needs.append(" + ".join(pair))
        if target is not R.EDEN_PRIME and options.mako_shuffled and not has(data.MAKO):
            needs.append("Mako")
        return needs


def _join(parts: list[str], limit: int) -> list[str]:
    """Pack comma-separated parts into lines of at most `limit` characters."""
    lines: list[str] = []
    for part in parts:
        if lines and len(lines[-1]) + 2 + len(part) <= limit:
            lines[-1] += ", " + part
        else:
            lines.append(part)
    return lines


def summary_lines(status: TrackerStatus, limit: int = 120, planets_shown: int = 5) -> list[str]:
    """The on-demand HUD summary: in-logic counts per region, the best uncharted planets, locked destinations."""
    by_region: Counter[str] = Counter()
    for area, count in status.areas.items():
        by_region[area_region(area)] += count.in_logic
    in_logic = [f"{'Uncharted' if region == R.UNCHARTED.value else region} {n}" for region, n in by_region.most_common() if n]
    lines = _join(["In logic: " + (in_logic[0] if in_logic else "nothing right now")] + in_logic[1:], limit)
    planets = sorted(((count.in_logic, area) for area, count in status.areas.items()
                      if area in UNCHARTED_PLANETS and count.in_logic), key=lambda p: (-p[0], p[1]))
    if planets:
        shown = [f"{area} {n}" for n, area in planets[:planets_shown]]
        more = f" (+{len(planets) - planets_shown} planets)" if len(planets) > planets_shown else ""
        lines += _join([f"Uncharted: {shown[0]}"] + shown[1:-1] + [shown[-1] + more] if len(shown) > 1
                       else [f"Uncharted: {shown[0]}{more}"], limit)
    order = [r.value for r in R]
    locked = [f"{region} [{', '.join(needs)}]" for region, needs in sorted(status.blockers.items(), key=lambda kv: order.index(kv[0]))
              if needs and region != R.FINAL_CITADEL.value]  # the finale is behind Ilos
    if locked:
        lines += _join(["Locked: " + locked[0]] + locked[1:], limit)
    if status.ilos_open:
        lines.append("Ilos is open: reach the Conduit")
    return lines


def area_line(status: TrackerStatus, area: str) -> str:
    """The landing notice for one area."""
    count = status.area(area)
    if not count.in_logic and not count.locked:
        return f"{area}: no checks left"
    text = f"{area}: {count.in_logic} check{'s' if count.in_logic != 1 else ''} in logic"
    return text + (f", {count.locked} locked" if count.locked else "")
