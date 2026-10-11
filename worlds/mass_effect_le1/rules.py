from __future__ import annotations

from typing import TYPE_CHECKING

from rule_builder.rules import Has

from . import data, uncharted
from .regions import location_included

if TYPE_CHECKING:
    from .world import MassEffectLE1World

HAS_ACT1 = Has(data.EVENT_ACT1)
# Scenes that only happen with that squadmate along (generated tables do not carry it).
NEEDS_SQUADMATE = {
    "Virmire: Wrex and the Genophage: Started": "Urdnot Wrex",  # bools 3015/3021/5472: Kirrahe's camp, Wrex's standoff
}
UNCHARTED_GATES = {  # landing conditions of gated uncharted planets (uncharted.py)
    uncharted.FEROS: Has(data.EVENT_FEROS),
    uncharted.NOVERIA: Has(data.EVENT_NOVERIA),
    uncharted.GARRUS: Has("Garrus Vakarian"),
}


def set_rules(world: MassEffectLE1World) -> None:
    # Entrance rules are set when regions are created (regions.ENTRANCES).
    for name, loc in data.LOCATIONS.items():
        if not location_included(world, loc):
            continue
        rule = None
        if loc.needs_act1:
            rule = HAS_ACT1
        if loc.needs_event is not None:
            rule = Has(loc.needs_event) if rule is None else rule & Has(loc.needs_event)
        if loc.squad is not None:  # the squadmate's own conversation
            rule = Has(loc.squad) if rule is None else rule & Has(loc.squad)
        if (needed := NEEDS_SQUADMATE.get(name)) is not None:
            rule = Has(needed) if rule is None else rule & Has(needed)
        if (gate := uncharted.location_gate(name)) is not None:
            rule = UNCHARTED_GATES[gate] if rule is None else rule & UNCHARTED_GATES[gate]
        if rule is not None:
            world.set_rule(world.get_location(name), rule)
    world.set_completion_rule(Has(data.EVENT_VICTORY))
