from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Item, LocationProgressType

from . import data

if TYPE_CHECKING:
    from .world import MassEffectLE1World


class MassEffectLE1Item(Item):
    game = data.GAME_NAME


def create_item(world: MassEffectLE1World, name: str) -> MassEffectLE1Item:
    return MassEffectLE1Item(name, data.ITEMS[name].classification, data.ITEM_NAME_TO_ID[name], world.player)


def create_items(world: MassEffectLE1World) -> None:
    pool: list[MassEffectLE1Item] = []
    for name, item in data.ITEMS.items():
        pool += [create_item(world, name) for _ in range(item.count)]

    if world.options.human_squad_at_citadel:
        pool = [item for item in pool if item.name not in data.HUMAN_SQUAD]
    if not world.options.bring_down_the_sky:
        pool = [item for item in pool if item.name != data.COORDINATES[data.Region.ASTEROID_X57]]
    if world.options.mako_shuffled:
        pool.append(create_item(world, data.MAKO))
    pool += [create_item(world, data.FRAGMENT) for _ in range(world.options.fragments_total.value)]

    unfilled = len(world.multiworld.get_unfilled_locations(world.player))
    if len(pool) > unfilled:
        # generate_early already guarantees room; this guards future table edits
        raise RuntimeError(f"{data.GAME_NAME}: {len(pool)} items for {unfilled} locations")

    # Gear and upgrades are useful items: they cannot go to excluded locations, which keep that many filler slots.
    excluded = sum(1 for loc in world.multiworld.get_unfilled_locations(world.player)
                   if loc.progress_type == LocationProgressType.EXCLUDED)
    room = unfilled - excluded
    gear = draw_gear(world, max(0, min(world.options.gear_pool.value, room - len(pool))))
    pool += [create_item(world, name) for name in gear]
    world.gear_total = len(gear)
    upgrades = max(0, min(world.options.upgrade_count.value, room - len(pool)))
    pool += [create_item(world, data.UPGRADE) for _ in range(upgrades)]

    pool += [create_item(world, world.get_filler_item_name()) for _ in range(unfilled - len(pool))]
    world.multiworld.itempool += pool


SPECTRE_SHARE = 20  # about one gear item in twenty is Spectre gear (at least one when any gear is drawn)


def draw_gear(world: MassEffectLE1World, count: int) -> list[str]:
    """Draw `count` distinct gear lines: Spectre lines first (count // SPECTRE_SHARE, at least 1), then round-robin over
    the categories in a random order, each category's lines shuffled, so every category is represented."""
    if count <= 0:
        return []
    rng = world.random
    spectre = [line.name for line in data.GEAR_LINES if line.spectre]
    rng.shuffle(spectre)
    picked = spectre[:max(1, count // SPECTRE_SHARE)]

    by_category: dict[str, list[str]] = {}
    for line in data.GEAR_LINES:
        if not line.spectre:
            by_category.setdefault(line.category, []).append(line.name)
    queues = list(by_category.values())
    for queue in queues:
        rng.shuffle(queue)
    rng.shuffle(queues)
    while len(picked) < count and any(queues):
        for queue in queues:
            if queue and len(picked) < count:
                picked.append(queue.pop())
    return picked
