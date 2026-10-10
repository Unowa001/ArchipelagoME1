from BaseClasses import Tutorial
from worlds.AutoWorld import WebWorld

from .options import option_groups


class MassEffectLE1WebWorld(WebWorld):
    game = "Mass Effect Legendary Edition 1"
    theme = "partyTime"
    setup_en = Tutorial(
        "Multiworld Setup Guide",
        "A guide to setting up Mass Effect (Legendary Edition) for MultiWorld.",
        "English",
        "setup_en.md",
        "setup/en",
        ["Jerrod"],
    )
    tutorials = [setup_en]
    option_groups = option_groups
