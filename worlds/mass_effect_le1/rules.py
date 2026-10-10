from __future__ import annotations

from typing import TYPE_CHECKING

from rule_builder.rules import Has

from . import data
from .regions import location_included

if TYPE_CHECKING:
    from .world import MassEffectLE1World

HAS_ACT1 = Has(data.EVENT_ACT1)


def set_rules(world: MassEffectLE1World) -> None:
    # Entrance rules are set when regions are created (regions.ENTRANCES).
    for name, loc in data.LOCATIONS.items():
        if not location_included(world, loc):
            continue
        rule = None
        if loc.needs_act1:
            rule = HAS_ACT1
        if loc.squad is not None:  # the squadmate's own conversation
            rule = Has(loc.squad) if rule is None else rule & Has(loc.squad)
        if rule is not None:
            world.set_rule(world.get_location(name), rule)
    world.set_completion_rule(Has(data.EVENT_VICTORY))
