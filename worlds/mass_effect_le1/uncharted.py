"""Uncharted planets whose landing needs more than Act 1 and the Mako (logic pass, 2026-10-11).

V-LE: each uncharted planet's landing condition is its `GalaxyMap_Planet` UsablePlanet column (`Engine.pcc`); 18 planets
gate on a plot bool instead of conditional 974 (TRUE). What sets each bool decides the rule here:
- Feros_Done 2507: Nodacrux (map 80), Chasca (81), MSV Cornucopia (FRE31 = map 101).
- Noveria_Done 2508: Altahe (24), Nepmos (73); the Unidentified Space Facility (FRE35 = map 105) needs conditional 1717,
  bools 7173 (Listening Post Alpha, Nepmos) and 4911 (Listening Post Theta, Altahe).
- Garrus's transponder 4637 (his Normandy conversation, transition 3703): MSV Fedele (FRE34 = map 104).
- Normandy transmissions, fired by the mod's open start instead (transitions 2971, 3188, 3218): Luna (51), Binthu (92),
  MSV Ontario (FRE32 = map 102). No rule.
- Set from always-landable planets, the Citadel (Act 1) or Binthu, so no rule: Solcrum (55), Xawin (11, MSV Majesty
  survey), Klensal (10) and Mavigon (13) (Citadel crime boss), Amaranthine (31), Nepheron (62), Edolus (25).
- Presrop (54): bool 4898 is only set by Kismet inside Presrop's own level (transition 3221), so how it opens is
  unknown. Its checks hold filler only until an in-game test settles it.
"""
from __future__ import annotations

import re

from .containers import CONTAINERS

FEROS = "feros"
NOVERIA = "noveria"
GARRUS = "garrus"

MAP_GATES: dict[int, str] = {80: FEROS, 81: FEROS, 101: FEROS, 24: NOVERIA, 73: NOVERIA, 105: NOVERIA, 104: GARRUS}
UNVERIFIED_MAPS = frozenset({54})

# Uncharted journal checks set only on a gated planet (sweep of every codex/journal setter in research/le1_*_uses.tsv;
# Listening Post Alpha: Started also has a Normandy transmission source, kept on Noveria to be safe).
JOURNAL_GATES: dict[str, str] = {
    "Investigate Samples: Completed": FEROS,  # bool 4606, transition 2877, only in BIOA_UNC81_04_DSG (Chasca)
    "UNC: Derelict Freighter: Started": FEROS,
    "UNC: Derelict Freighter: Completed": FEROS,
    "UNC: Listening Post Alpha: Started": NOVERIA,
    "UNC: Listening Post Alpha: Completed": NOVERIA,
    "UNC: Listening Post Theta: Started": NOVERIA,
    "UNC: Listening Post Theta: Completed": NOVERIA,
    "Garrus: Find Dr. Saleon: Completed": GARRUS,
}

_LEVEL = re.compile(r"BIOA_(UNC|FRE)(\d\d)")


def map_number(level_key: str) -> int | None:
    """Galaxy-map Map row of a level package: BIOA_UNCnn is map nn, BIOA_FRE31-35 are maps 101-105."""
    match = _LEVEL.match(level_key)
    if match is None:
        return None
    number = int(match.group(2))
    return number if match.group(1) == "UNC" else number + 70


# Container and drop-slot location names -> galaxy-map Map row.
_CONTAINER_MAP: dict[str, int] = {}
for _entry in CONTAINERS:
    _number = map_number(_entry.key)
    if _number is not None:
        _CONTAINER_MAP[_entry.name] = _number
        for _roll in range(2, _entry.drops + 1):
            _CONTAINER_MAP[f"{_entry.name} (Item {_roll})"] = _number


def location_gate(name: str) -> str | None:
    """FEROS, NOVERIA or GARRUS when this location sits on a gated uncharted planet, else None."""
    number = _CONTAINER_MAP.get(name)
    return MAP_GATES.get(number) if number is not None else JOURNAL_GATES.get(name)


def location_unverified(name: str) -> bool:
    """On a planet whose landing condition is not understood yet (filler only)."""
    return _CONTAINER_MAP.get(name) in UNVERIFIED_MAPS
