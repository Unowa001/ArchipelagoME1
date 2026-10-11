import random

from BaseClasses import CollectionState

from ..data import COORDINATES, FRAGMENT, LOCATION_NAME_TO_ID, Region, SQUAD
from ..tracker import Tracker, area_line, level_area, location_area, summary_lines
from . import MassEffectLE1TestBase


class TrackerTestBase(MassEffectLE1TestBase):
    def tracker(self) -> Tracker:
        return Tracker(self.world.fill_slot_data())

    def all_missing(self) -> list[int]:
        return [loc.address for loc in self.multiworld.get_locations(self.player) if loc.address is not None]

    def item_ids(self, *names: str) -> list[int]:
        return [self.world.item_name_to_id[name] for name in names]


class TestTrackerMatchesGeneration(TrackerTestBase):
    options = {"required_squad_size": 2, "mako_shuffled": True}

    def test_rebuilt_logic_agrees_with_the_seed(self) -> None:
        """For random sets of received items, every seed location is in logic in the client's rebuild exactly when
        it is in the generated world's own logic."""
        tracker = self.tracker()
        pool = [item for item in self.multiworld.itempool if item.player == self.player]
        rng = random.Random(7)
        for size in (0, 5, 15, 40, len(pool)):
            items = rng.sample(pool, min(size, len(pool)))
            state = CollectionState(self.multiworld)
            for item in items:
                state.collect(item, prevent_sweep=True)
            state.sweep_for_advancements()
            rebuilt = tracker.state([item.code for item in items])
            for loc in self.multiworld.get_locations(self.player):
                if loc.address is None:
                    continue
                with self.subTest(size=size, location=loc.name):
                    self.assertEqual(loc.can_reach(state), tracker.multiworld.get_location(loc.name, 1).can_reach(rebuilt))

    def test_blockers_are_empty_exactly_when_the_destination_opens(self) -> None:
        tracker = self.tracker()
        pool = [item.code for item in self.multiworld.itempool if item.player == self.player]
        rng = random.Random(3)
        for size in (0, 3, 10, 30, 80, len(pool)):
            state = tracker.state(rng.sample(pool, min(size, len(pool))))
            for region in Region:
                with self.subTest(size=size, region=region.value):
                    reachable = tracker.multiworld.get_region(region.value, 1).can_reach(state)
                    self.assertEqual(reachable, not tracker.blockers(region.value, state))


class TestTrackerStatus(TrackerTestBase):
    options = {"required_squad_size": 2}

    def test_fresh_start(self) -> None:
        status = self.tracker().status([], self.all_missing())
        self.assertGreater(status.area(Region.NORMANDY.value).in_logic, 0)
        self.assertGreater(status.area(Region.CITADEL.value).in_logic, 0)  # open from the start, Act 1 included
        self.assertEqual(status.blockers[Region.FEROS.value], ["coords", "2 squad"])
        self.assertNotIn(Region.UNCHARTED.value, status.blockers)  # Act 1 + Mako (not shuffled): in logic
        self.assertFalse(status.ilos_open)

    def test_items_and_checks_update_the_counts(self) -> None:
        tracker = self.tracker()
        missing = self.all_missing()
        status = tracker.status(self.item_ids(COORDINATES[Region.FEROS], SQUAD[2], SQUAD[3]), missing)
        self.assertNotIn(Region.FEROS.value, status.blockers)
        feros = status.area(Region.FEROS.value).in_logic
        self.assertGreater(feros, 0)
        done = LOCATION_NAME_TO_ID["Feros: Defeat the Thorian"]
        after = tracker.status(self.item_ids(COORDINATES[Region.FEROS], SQUAD[2], SQUAD[3]), [i for i in missing if i != done])
        self.assertEqual(after.area(Region.FEROS.value).in_logic, feros - 1)

    def test_duplicate_squadmates_count_like_generation(self) -> None:
        tracker = self.tracker()
        state = tracker.state(self.item_ids(COORDINATES[Region.FEROS], SQUAD[2], SQUAD[2]))
        self.assertTrue(tracker.multiworld.get_region(Region.FEROS.value, 1).can_reach(state))
        self.assertEqual(tracker.blockers(Region.FEROS.value, state), [])

    def test_fragments_and_ilos(self) -> None:
        status = self.tracker().status(self.item_ids(FRAGMENT), self.all_missing())
        self.assertEqual(status.fragments, 1)
        self.assertIn(f"fragments 1/{self.world.fragments_required}", status.blockers[Region.ILOS.value])
        self.assertIn("finish Virmire", status.blockers[Region.ILOS.value])


class TestTrackerMakoShuffled(TrackerTestBase):
    options = {"mako_shuffled": True}

    def test_uncharted_waits_for_the_mako(self) -> None:
        status = self.tracker().status([], self.all_missing())
        self.assertEqual(status.blockers[Region.UNCHARTED.value], ["Mako"])


class TestTrackerText(TrackerTestBase):
    def test_summary_lines_fit_the_hud(self) -> None:
        tracker = self.tracker()
        for received in ([], [item.code for item in self.multiworld.itempool if item.player == self.player]):
            lines = summary_lines(tracker.status(received, self.all_missing()))
            self.assertTrue(lines[0].startswith("In logic: "))
            self.assertTrue(all(0 < len(line) <= 120 for line in lines), lines)

    def test_area_line(self) -> None:
        status = self.tracker().status([], self.all_missing())
        self.assertRegex(area_line(status, Region.NORMANDY.value), r"^Normandy: \d+ checks? in logic")
        self.assertEqual(area_line(status, "Nowhere"), "Nowhere: no checks left")


class TestAreas(MassEffectLE1TestBase):
    def test_level_area(self) -> None:
        self.assertEqual(level_area("BIOA_WAR20_03_DSG"), "Feros")
        self.assertEqual(level_area("bioa_sta30_03a_dsg"), "Citadel")
        self.assertEqual(level_area("BIOA_UNC52_00_DSG"), "Asteroid X57")
        self.assertEqual(level_area("BIOA_UNC81_04_DSG"), "Chasca")
        self.assertEqual(level_area("BIOA_FRE34"), "MSV Fedele")
        self.assertIsNone(level_area("BIOA_FRONTEND"))

    def test_uncharted_containers_count_per_planet(self) -> None:
        from ..data import LOCATIONS
        self.assertEqual(location_area("Chasca: Crate 1", LOCATIONS["Chasca: Crate 1"]), "Chasca")
        self.assertEqual(location_area("Asteroid X57: Crate 1", LOCATIONS["Asteroid X57: Crate 1"]), "Asteroid X57")
