from dataclasses import dataclass

from Options import Choice, DefaultOnToggle, OptionGroup, PerGameCommonOptions, Range, Toggle


class FragmentsTotal(Range):
    """How many Prothean Beacon Fragments are shuffled into the item pool."""

    display_name = "Beacon Fragments in Pool"
    range_start = 1
    range_end = 12
    default = 6


class FragmentsRequired(Range):
    """How many Prothean Beacon Fragments unlock Ilos. Lowered to the pool size if it is larger."""

    display_name = "Beacon Fragments Required"
    range_start = 1
    range_end = 12
    default = 4


class RequiredSquadSize(Range):
    """How many squadmates logic expects before landing on a mission world (Eden Prime and the Citadel excepted).

    Provisional until the S0 spike shows how the game handles landing with fewer than two squadmates."""

    display_name = "Required Squad Size"
    range_start = 0
    range_end = 2
    default = 2


class MakoShuffled(Toggle):
    """Shuffle the M35 Mako into the item pool. When off, the Mako is available from the start.

    Most mission worlds have a Mako section, so turning this on gates nearly everything behind one item."""

    display_name = "Shuffle the Mako"


class HumanSquadAtCitadel(Toggle):
    """Kaidan and Ashley are not items: the vanilla first Citadel arrival recruits both (owner decision 2026-10-09).

    Logic treats them as earned on reaching the Citadel; Garrus, Wrex, Tali and Liara stay items."""

    display_name = "Kaidan and Ashley Join at the Citadel"


class BringDownTheSky(DefaultOnToggle):
    """Include the Bring Down the Sky content (Asteroid X57)."""

    display_name = "Include Bring Down the Sky"


class Codexsanity(Choice):
    """Codex pages are checks: unlocking a page sends it.

    story: pages from the Citadel, the story planets and squadmate conversations on the Normandy (94).
    full: also Normandy crew and terminals, uncharted worlds and side-assignment transmissions (119)."""

    display_name = "Codexsanity"
    option_off = 0
    option_story = 1
    option_full = 2
    default = 2


class Journalsanity(Choice):
    """Journal entries are checks: each quest's first entry (Started) and its completion (Completed). A story choice can
    skip a completion (a failed assignment), so completions only hold filler.

    story: Citadel, story planet and squadmate quests. full: also uncharted-world assignments."""

    display_name = "Journalsanity"
    option_off = 0
    option_story = 1
    option_full = 2
    default = 2


class Containersanity(Choice):
    """Containers that need no Decryption (crates, kits, ammo packs, malfunctioning objects...) are checks: opening one
    sends it. Vanilla loot stays inside.

    with_drops: each container also counts once per treasure roll it makes (crates 3, kits 2, ...), all sent on open."""

    display_name = "Containersanity"
    option_off = 0
    option_on = 1
    option_with_drops = 2
    default = 1


class AidStations(DefaultOnToggle):
    """Aid Stations (medi-gel refills) that need no Decryption are checks: using one sends it."""

    display_name = "Aid Stations"


class UnlockContainers(DefaultOnToggle):
    """Containers and Aid Stations locked behind Decryption open like plain ones (no skill, no minigame), and become
    checks under Containersanity / Aid Stations (179 more)."""

    display_name = "Unlock Containers"


class GearPool(Range):
    """How many gear items (one manufacturer's weapon, armor, bio-amp or omni-tool line each) are drawn into the pool.

    Every category is represented; about one in twenty is Spectre gear. Gear arrives at a level that climbs from I to X
    as you collect it (Spectre gear is always X). Lowered to the free room in the pool."""

    display_name = "Gear Items"
    range_start = 0
    range_end = 243
    default = 80


class UpgradeCount(Range):
    """How many Random Upgrade items (a weapon, ammo, armor or grenade mod) are in the pool. Lowered to the free room
    left after gear."""

    display_name = "Random Upgrades"
    range_start = 0
    range_end = 100
    default = 20


@dataclass
class MassEffectLE1Options(PerGameCommonOptions):
    fragments_total: FragmentsTotal
    fragments_required: FragmentsRequired
    required_squad_size: RequiredSquadSize
    mako_shuffled: MakoShuffled
    human_squad_at_citadel: HumanSquadAtCitadel
    bring_down_the_sky: BringDownTheSky
    codexsanity: Codexsanity
    journalsanity: Journalsanity
    containersanity: Containersanity
    aid_stations: AidStations
    unlock_containers: UnlockContainers
    gear_pool: GearPool
    upgrade_count: UpgradeCount


option_groups = [
    OptionGroup("Goal", [FragmentsTotal, FragmentsRequired]),
    OptionGroup("Logic", [RequiredSquadSize, MakoShuffled, HumanSquadAtCitadel, BringDownTheSky]),
    OptionGroup("Checks", [Codexsanity, Journalsanity, Containersanity, AidStations, UnlockContainers]),
    OptionGroup("Items", [GearPool, UpgradeCount]),
]
