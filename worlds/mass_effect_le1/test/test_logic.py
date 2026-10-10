from ..data import COORDINATES, EVENT_ACT1, EVENT_VIRMIRE, FILLER, FRAGMENT, GEAR_BY_NAME, HUMAN_SQUAD, LOCATIONS, Region, SQUAD, UPGRADE
from BaseClasses import LocationProgressType
from . import MassEffectLE1TestBase


class TestDefaults(MassEffectLE1TestBase):
    def test_citadel_is_open_from_start(self) -> None:
        self.assertTrue(self.can_reach_region(Region.CITADEL.value))
        self.assertTrue(self.can_reach_location("Citadel: Recruit Garrus"))

    def collect_event(self, name: str) -> None:
        self.collect(self.multiworld.get_location(name, self.player).item)

    def test_act1_gates_citadel_side_content(self) -> None:
        self.assertFalse(self.can_reach_location("Citadel: Asari Consort"))
        self.collect_event(EVENT_ACT1)
        self.assertTrue(self.can_reach_location("Citadel: Asari Consort"))

    def test_eden_prime_needs_only_coordinates(self) -> None:
        self.assertFalse(self.can_reach_region(Region.EDEN_PRIME.value))
        self.collect_by_name(COORDINATES[Region.EDEN_PRIME])
        self.assertTrue(self.can_reach_region(Region.EDEN_PRIME.value))

    def test_mission_needs_coordinates_and_two_squadmates(self) -> None:
        self.collect_by_name(COORDINATES[Region.FEROS])
        self.assertFalse(self.can_reach_region(Region.FEROS.value))
        self.collect_by_name(SQUAD[2])
        self.assertFalse(self.can_reach_region(Region.FEROS.value))
        self.collect_by_name(SQUAD[3])
        self.assertTrue(self.can_reach_region(Region.FEROS.value))

    def test_virmire_needs_kaidan_and_ashley(self) -> None:
        self.collect_by_name([COORDINATES[Region.VIRMIRE], "Garrus Vakarian", "Urdnot Wrex"])
        self.assertFalse(self.can_reach_region(Region.VIRMIRE.value))
        self.collect_by_name("Kaidan Alenko")
        self.assertFalse(self.can_reach_region(Region.VIRMIRE.value))
        self.collect_by_name("Ashley Williams")
        self.assertTrue(self.can_reach_region(Region.VIRMIRE.value))

    def test_ilos_needs_required_fragments(self) -> None:
        self.collect_by_name(["Garrus Vakarian", "Urdnot Wrex"])
        self.collect_event(EVENT_VIRMIRE)
        fragments = self.get_items_by_name(FRAGMENT)
        self.assertEqual(len(fragments), 6)
        self.collect(fragments[:3])
        self.assertFalse(self.can_reach_region(Region.ILOS.value))
        self.collect(fragments[3:4])
        self.assertTrue(self.can_reach_region(Region.ILOS.value))

    def test_ilos_needs_virmire_complete(self) -> None:
        self.collect_by_name(["Garrus Vakarian", "Urdnot Wrex"])
        self.collect(self.get_items_by_name(FRAGMENT))
        self.assertFalse(self.can_reach_region(Region.ILOS.value))
        self.collect_event(EVENT_VIRMIRE)
        self.assertTrue(self.can_reach_region(Region.ILOS.value))

    def test_beatable_with_everything(self) -> None:
        self.collect_all_but([])
        self.assertBeatable(True)


class TestMakoShuffled(MassEffectLE1TestBase):
    options = {"mako_shuffled": True}

    def test_missions_need_the_mako(self) -> None:
        self.collect_by_name([COORDINATES[Region.THERUM], "Garrus Vakarian", "Urdnot Wrex"])
        self.assertFalse(self.can_reach_region(Region.THERUM.value))
        self.collect_by_name("M35 Mako")
        self.assertTrue(self.can_reach_region(Region.THERUM.value))


class TestSoloSquad(MassEffectLE1TestBase):
    options = {"required_squad_size": 0}

    def test_missions_need_only_coordinates(self) -> None:
        self.collect_by_name(COORDINATES[Region.NOVERIA])
        self.assertTrue(self.can_reach_region(Region.NOVERIA.value))


class TestNoBringDownTheSky(MassEffectLE1TestBase):
    options = {"bring_down_the_sky": False}

    def test_x57_removed(self) -> None:
        self.assertNotIn("Asteroid X57: Bring Down the Sky", self.multiworld.regions.location_cache[self.player])
        self.assertEqual(self.get_items_by_name(COORDINATES[Region.ASTEROID_X57]), [])


class TestFragmentClamping(MassEffectLE1TestBase):
    options = {"fragments_total": 12, "fragments_required": 12, "mako_shuffled": True, "codexsanity": "off", "journalsanity": "off", "containersanity": "off",
               "aid_stations": False}

    def test_fragments_clamped_to_location_room(self) -> None:
        # 23 locations - 6 squad - 6 coordinates - 1 Mako - 4 reserved filler slots = 6
        self.assertEqual(len(self.get_items_by_name(FRAGMENT)), 6)
        self.assertEqual(self.world.fragments_required, 6)


class TestHumanSquadAtCitadel(MassEffectLE1TestBase):
    options = {"human_squad_at_citadel": True, "fragments_total": 12, "fragments_required": 12, "mako_shuffled": True,
               "codexsanity": "off", "journalsanity": "off", "containersanity": "off",
               "aid_stations": False}

    def test_kaidan_and_ashley_are_not_items(self) -> None:
        for name in HUMAN_SQUAD:
            self.assertEqual(self.get_items_by_name(name), [])
        for name in SQUAD[2:]:
            self.assertEqual(len(self.get_items_by_name(name)), 1)

    def test_citadel_arrival_gives_the_pair(self) -> None:
        for name in HUMAN_SQUAD:  # events (no ID): the client never sets their InParty
            self.assertIsNone(self.multiworld.get_location(f"Citadel: {name} Joins (arrival)", self.player).address)
        self.assertFalse(self.can_reach_region(Region.VIRMIRE.value))
        # Citadel is open from the start, so its arrival events count: no squad items needed (squad of two, D4 pair)
        self.collect_by_name([COORDINATES[Region.VIRMIRE], "M35 Mako"])
        self.assertTrue(self.can_reach_region(Region.VIRMIRE.value))

    def test_freed_slots_go_to_fragments_room(self) -> None:
        # 23 locations - 4 squad - 6 coordinates - 1 Mako - 4 reserved filler slots = 8
        self.assertEqual(len(self.get_items_by_name(FRAGMENT)), 8)


class TestGearDraw(MassEffectLE1TestBase):
    options = {"fragments_total": 1, "fragments_required": 1, "upgrade_count": 2, "codexsanity": "off", "journalsanity": "off", "containersanity": "off",
               "aid_stations": False}

    def test_gear_fills_the_free_room_with_distinct_lines_and_a_spectre(self) -> None:
        gear = [item.name for item in self.multiworld.itempool if item.name in GEAR_BY_NAME]
        self.assertEqual(len(gear), len(set(gear)))
        self.assertEqual(len(gear), self.world.gear_total)
        self.assertGreater(len(gear), 0)
        self.assertTrue(any(GEAR_BY_NAME[name].spectre for name in gear))
        upgrades = len(self.get_items_by_name(UPGRADE))
        filler = sum(1 for item in self.multiworld.itempool if item.name in FILLER)
        self.assertEqual(upgrades, min(2, upgrades + filler))  # upgrades take room left after gear, before filler
        self.assertEqual(self.world.fill_slot_data()["gear_total"], len(gear))

    def test_categories_are_spread_before_any_repeats(self) -> None:
        gear = [GEAR_BY_NAME[item.name] for item in self.multiworld.itempool if item.name in GEAR_BY_NAME]
        categories = [line.category for line in gear if not line.spectre]
        self.assertEqual(len(categories), len(set(categories)))  # fewer slots than the 12 categories here


class TestNoGear(MassEffectLE1TestBase):
    options = {"gear_pool": 0, "upgrade_count": 0}

    def test_no_gear_or_upgrades(self) -> None:
        self.assertFalse(any(item.name in GEAR_BY_NAME or item.name == UPGRADE for item in self.multiworld.itempool))
        self.assertEqual(self.world.gear_total, 0)


class TestGearSpread(MassEffectLE1TestBase):
    options = {"gear_pool": 70}

    def test_round_robin_keeps_categories_within_one(self) -> None:
        counts: dict[str, int] = {}
        for item in self.multiworld.itempool:
            if item.name in GEAR_BY_NAME and not GEAR_BY_NAME[item.name].spectre:
                counts[GEAR_BY_NAME[item.name].category] = counts.get(GEAR_BY_NAME[item.name].category, 0) + 1
        self.assertEqual(len(counts), 12)
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)


class TestCodexsanity(MassEffectLE1TestBase):
    def test_full_codex_is_in_and_squad_pages_need_the_squadmate(self) -> None:
        codex = [loc for loc in self.multiworld.get_locations(self.player) if loc.name.startswith("Codex: ")]
        self.assertEqual(len(codex), 119)
        page = next(name for name, loc in LOCATIONS.items() if loc.squad == "Garrus Vakarian")
        self.assertFalse(self.can_reach_location(page))
        self.collect_by_name(["Garrus Vakarian"])
        self.assertTrue(self.can_reach_location(page))

    def test_uncharted_waits_for_act1(self) -> None:
        self.assertFalse(self.can_reach_region(Region.UNCHARTED.value))


class TestCodexsanityStory(MassEffectLE1TestBase):
    options = {"codexsanity": "story"}

    def test_only_story_pages(self) -> None:
        codex = [loc.name for loc in self.multiworld.get_locations(self.player) if loc.name.startswith("Codex: ")]
        self.assertEqual(len(codex), 94)
        self.assertTrue(all(LOCATIONS[name].codex == "story" for name in codex))


class TestContainers(MassEffectLE1TestBase):
    def test_default_has_containers_and_stations_but_no_drop_slots(self) -> None:
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        containers = [n for n in names if LOCATIONS.get(n) and LOCATIONS[n].container == "container"]
        stations = [n for n in names if LOCATIONS.get(n) and LOCATIONS[n].container == "station"]
        self.assertEqual((len(containers), len(stations)), (226 + 158, 33 + 21))
        self.assertFalse(any(LOCATIONS[n].container == "drop" for n in names if n in LOCATIONS))

    def test_uncharted_containers_need_act1_and_x57_its_coordinates(self) -> None:
        self.assertFalse(self.can_reach_location("Chasca: Crate 1"))
        self.assertFalse(self.can_reach_location("Asteroid X57: Crate 1"))


class TestContainerDrops(MassEffectLE1TestBase):
    options = {"containersanity": "with_drops", "aid_stations": False}

    def test_drop_slots_share_their_container_flag(self) -> None:
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        self.assertIn("Chasca: Crate 1 (Item 3)", names)
        self.assertEqual(LOCATIONS["Chasca: Crate 1 (Item 3)"].ot_plot, LOCATIONS["Chasca: Crate 1"].ot_plot)
        self.assertFalse(any(LOCATIONS[n].container == "station" for n in names if n in LOCATIONS))


class TestUnlockContainers(MassEffectLE1TestBase):
    def test_locked_containers_and_stations_are_checks_by_default(self) -> None:
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        locked = [n for n in names if n in LOCATIONS and LOCATIONS[n].locked]
        self.assertEqual(len(locked), 179)
        self.assertTrue(self.world.fill_slot_data()["unlock_containers"])


class TestKeepLocks(MassEffectLE1TestBase):
    options = {"unlock_containers": False}

    def test_locked_ones_are_left_out(self) -> None:
        self.assertFalse(any(n in LOCATIONS and LOCATIONS[n].locked for n in
                             (loc.name for loc in self.multiworld.get_locations(self.player))))


class TestJournalsanity(MassEffectLE1TestBase):
    def test_journal_checks_and_excluded_completions(self) -> None:
        journal = [loc for loc in self.multiworld.get_locations(self.player) if LOCATIONS.get(loc.name) and LOCATIONS[loc.name].journal]
        self.assertEqual(len(journal), 130)
        for loc in journal:
            self.assertEqual(loc.progress_type == LocationProgressType.EXCLUDED, loc.name.endswith(": Completed"))

    def test_squad_quest_needs_its_squadmate(self) -> None:
        self.assertFalse(self.can_reach_location("Wrex: Family Armor: Started"))
        self.collect_by_name(["Urdnot Wrex"])
        self.assertTrue(self.can_reach_location("Wrex: Family Armor: Started"))
