import logging
from types import SimpleNamespace
import unittest

from ..client import (
    BridgeConnection,
    GameNotReadyError,
    ID_BASE,
    ME1Context,
    coordinate_bool_for_item,
    FRAGMENT_ITEM_ID,
    ILOS_OPEN_PLOT_BOOL,
    plot_bool_for_item,
    sync_ilos_gate,
    evaluate_location_predicates,
    parse_plot_predicate,
    sync_received_items,
    gear_level,
    upgrade_row,
)
from ..data import ITEM_NAME_TO_ID, LOCATION_NAME_TO_ID, UPGRADE
from ..gear import GEAR_LINES


class FakeBridge:
    def __init__(self, *, bools=None, ints=None, fail_give_after=None):
        self.bools = dict(bools or {})
        self.ints = dict(ints or {})
        self.bool_writes = []
        self.int_writes = []
        self.gives = []
        self.resources = []
        self.fail_give_after = fail_give_after

    def give_item(self, item_row, sophistication, manufacturer_row):
        if self.fail_give_after is not None and len(self.gives) >= self.fail_give_after:
            raise GameNotReadyError("load screen")
        self.gives.append((item_row, sophistication, manufacturer_row))

    def add_resource(self, resource, amount):
        self.resources.append((resource, amount))

    def ping(self):
        pass

    def close(self):
        pass

    def get_bool(self, index):
        return self.bools.get(index, False)

    def get_int(self, index):
        return self.ints.get(index, 0)

    def set_bool(self, index, value):
        self.bool_writes.append((index, value))
        self.bools[index] = value

    def set_int(self, index, value):
        self.int_writes.append((index, value))
        self.ints[index] = value


class FakePipe:
    def __init__(self, reply=b"OK 1", fail_write=False):
        self.reply = reply
        self.fail_write = fail_write
        self.writes = []
        self.closed = False

    def write(self, value):
        if self.fail_write:
            raise OSError("disconnected")
        self.writes.append(value)

    def read(self, _size):
        return self.reply

    def close(self):
        self.closed = True


class TestBridgeConnection(unittest.TestCase):
    def test_reconnects_once_after_transport_failure(self):
        broken = FakePipe(fail_write=True)
        working = FakePipe(b"OK 1")
        pipes = iter((broken, working))
        bridge = BridgeConnection(opener=lambda *_args: next(pipes))

        self.assertTrue(bridge.get_bool(2505))
        self.assertTrue(broken.closed)
        self.assertEqual(working.writes, [b"GETB 2505"])

    def test_noworld_is_game_not_ready(self):
        bridge = BridgeConnection(opener=lambda *_args: FakePipe(b"ERR noworld"))

        with self.assertRaises(GameNotReadyError):
            bridge.get_int(2000)


class TestPredicates(unittest.TestCase):
    def test_parse_supported_forms(self):
        self.assertEqual(parse_plot_predicate("bool 2505 Prologue_Done").indices, (2505,))
        self.assertEqual(parse_plot_predicate("bool 3798 or 4133").indices, (3798, 4133))
        predicate = parse_plot_predicate("int 39 >= 20 (keeper note)")
        self.assertEqual((predicate.kind, predicate.indices, predicate.threshold), ("int", (39,), 20))

    def test_rejects_unsupported_forms(self):
        self.assertIsNone(parse_plot_predicate(None))
        self.assertIsNone(parse_plot_predicate("AP check flag (P8) at recruitment"))

    def test_evaluate_bool_or_and_int(self):
        bridge = FakeBridge(bools={4133: True}, ints={39: 20})

        self.assertTrue(parse_plot_predicate("bool 3798 or 4133").evaluate(bridge))
        self.assertTrue(parse_plot_predicate("int 39 >= 20").evaluate(bridge))
        self.assertFalse(parse_plot_predicate("int 39 >= 21").evaluate(bridge))

    def test_location_evaluation_uses_data_predicates(self):
        bridge = FakeBridge(bools={3569: True, 3798: True})

        result = evaluate_location_predicates(bridge)

        self.assertIn(LOCATION_NAME_TO_ID["Eden Prime: Beacon Vision"], result)
        self.assertIn(LOCATION_NAME_TO_ID["Feros: Confront Shiala"], result)
        self.assertNotIn(LOCATION_NAME_TO_ID["Citadel: Recruit Garrus"], result)

    def test_vanilla_recruit_counts_only_without_the_item(self):
        bridge = FakeBridge(bools={3941: True, 3942: True})  # InParty Garrus, Wrex
        garrus, wrex = LOCATION_NAME_TO_ID["Citadel: Recruit Garrus"], LOCATION_NAME_TO_ID["Citadel: Recruit Wrex"]

        self.assertTrue({garrus, wrex} <= evaluate_location_predicates(bridge))
        # The client wrote Garrus's InParty itself after receiving his item: not a vanilla recruitment.
        result = evaluate_location_predicates(bridge, {ITEM_NAME_TO_ID["Garrus Vakarian"]})
        self.assertNotIn(garrus, result)
        self.assertIn(wrex, result)


class TestReceivedItems(unittest.TestCase):
    def test_coordinate_item_mapping(self):
        self.assertEqual(coordinate_bool_for_item(ID_BASE + 0x10), 20000)
        self.assertEqual(coordinate_bool_for_item(ID_BASE + 0x15), 20005)
        self.assertIsNone(coordinate_bool_for_item(ID_BASE + 0x16))
        self.assertIsNone(coordinate_bool_for_item(ID_BASE + 0x00))

    def test_resumes_at_saved_index_and_advances_past_unsupported_items(self):
        bridge = FakeBridge(ints={2000: 1})
        items = [
            SimpleNamespace(item=ID_BASE + 0x10),
            SimpleNamespace(item=ID_BASE + 0x20),  # fragment: no game write
            SimpleNamespace(item=ID_BASE + 0x12),
        ]

        result = sync_received_items(bridge, items, logging.getLogger("test"))

        self.assertEqual(result, 3)
        self.assertEqual(bridge.bool_writes, [(20002, True)])
        self.assertEqual(bridge.int_writes, [(2000, 2), (2000, 3)])

    def test_older_save_replays_items_without_duplicate_progress(self):
        bridge = FakeBridge(ints={2000: 0})
        items = [SimpleNamespace(item=ID_BASE + 0x10), SimpleNamespace(item=ID_BASE + 0x11)]

        sync_received_items(bridge, items)
        sync_received_items(bridge, items)

        self.assertEqual(bridge.bool_writes, [(20000, True), (20001, True)])
        self.assertEqual(bridge.int_writes, [(2000, 1), (2000, 2)])

    def test_index_ahead_of_server_is_not_lowered(self):
        bridge = FakeBridge(ints={2000: 7})

        result = sync_received_items(bridge, [SimpleNamespace(item=ID_BASE + 0x10)])

        self.assertEqual(result, 7)
        self.assertEqual(bridge.bool_writes, [])
        self.assertEqual(bridge.int_writes, [])


class TestGearDelivery(unittest.TestCase):
    PISTOL = next(line for line in GEAR_LINES if line.category == "Pistol" and not line.spectre)
    SPECTRE = next(line for line in GEAR_LINES if line.spectre)

    def test_gear_levels_climb_from_one_to_ten_over_the_seed(self):
        self.assertEqual([gear_level(seen, 4) for seen in range(4)], [1, 4, 7, 10])
        self.assertEqual(gear_level(0, 1), 1)
        self.assertEqual(gear_level(50, 10), 10)

    def test_gear_spectre_upgrade_and_credits_reach_the_bridge(self):
        bridge = FakeBridge()
        items = [SimpleNamespace(item=ITEM_NAME_TO_ID[name]) for name in
                 (self.PISTOL.name, self.SPECTRE.name, UPGRADE, "Credits", "Omni-Gel")]

        sync_received_items(bridge, items, gear_total=3, seed_name="S")

        self.assertEqual(bridge.gives[0], (self.PISTOL.item_row, 1, self.PISTOL.manufacturer_row))
        self.assertEqual(bridge.gives[1], (self.SPECTRE.item_row, 10, self.SPECTRE.manufacturer_row))
        self.assertEqual(bridge.gives[2], (upgrade_row("S", 2), 10, -1))  # two of three gear lines seen
        self.assertEqual(bridge.resources, [(0, 5000), (2, 10)])
        self.assertEqual(bridge.int_writes[-1], (2000, 5))

    def test_replay_from_an_older_save_gives_the_same_items_at_the_same_levels(self):
        items = [SimpleNamespace(item=ITEM_NAME_TO_ID[name]) for name in (self.PISTOL.name, UPGRADE, self.PISTOL.name)]
        first, replay = FakeBridge(), FakeBridge()
        sync_received_items(first, items, gear_total=2, seed_name="S")
        sync_received_items(replay, items, gear_total=2, seed_name="S")
        self.assertEqual(first.gives, replay.gives)
        self.assertEqual([give[1] for give in first.gives], [1, 10, 10])

    def test_failed_delivery_resumes_at_the_failed_item(self):
        bridge = FakeBridge(fail_give_after=1)
        items = [SimpleNamespace(item=ITEM_NAME_TO_ID[self.PISTOL.name])] * 3

        with self.assertRaises(GameNotReadyError):
            sync_received_items(bridge, items, gear_total=3)
        self.assertEqual(bridge.ints[2000], 1)
        bridge.fail_give_after = None
        sync_received_items(bridge, items, gear_total=3)
        self.assertEqual([give[1] for give in bridge.gives], [1, 5, 10])


class TestContextPolling(unittest.IsolatedAsyncioTestCase):
    async def test_poll_sends_new_checks_and_goal(self):
        bridge = FakeBridge(bools={3569: True, 6530: True}, ints={2000: 0})
        ctx = object.__new__(ME1Context)
        ctx.bridge = bridge
        ctx.items_received = []
        ctx.checked_locations = set()
        ctx.locations_checked = set()
        ctx.server_locations = set()
        ctx.finished_game = False
        ctx.slot = 1
        ctx.server = SimpleNamespace(socket=SimpleNamespace(closed=False))
        ctx.fragments_required = None
        sent = []

        async def capture(messages):
            sent.extend(messages)

        ctx.send_msgs = capture
        await ctx.poll_game()

        beacon = LOCATION_NAME_TO_ID["Eden Prime: Beacon Vision"]
        location_packets = [packet for packet in sent if packet["cmd"] == "LocationChecks"]
        goal_packets = [packet for packet in sent if packet["cmd"] == "StatusUpdate"]
        self.assertIn(beacon, location_packets[0]["locations"])
        self.assertEqual(len(goal_packets), 1)
        self.assertTrue(ctx.finished_game)

        await ctx.poll_game()
        self.assertEqual(len([packet for packet in sent if packet["cmd"] == "StatusUpdate"]), 1)

    async def test_poll_without_server_slot_neither_writes_nor_sends(self):
        bridge = FakeBridge(bools={3569: True, 6530: True}, ints={2000: 0})
        ctx = object.__new__(ME1Context)
        ctx.bridge = bridge
        ctx.items_received = [SimpleNamespace(item=ID_BASE + 0x13)]
        ctx.checked_locations = set()
        ctx.locations_checked = set()
        ctx.server_locations = set()
        ctx.finished_game = False
        ctx.slot = None
        ctx.server = None
        sent = []

        async def capture(messages):
            sent.extend(messages)

        ctx.send_msgs = capture
        await ctx.poll_game()

        self.assertEqual(sent, [])
        self.assertEqual(bridge.bool_writes, [])
        self.assertEqual(bridge.int_writes, [])
        self.assertFalse(ctx.finished_game)
        self.assertEqual(ctx.locations_checked, set())


class TestSquadAndIlos(unittest.TestCase):
    def test_squad_items_map_to_inparty_bools(self):
        self.assertEqual(plot_bool_for_item(ITEM_NAME_TO_ID["Kaidan Alenko"]), 3939)
        self.assertEqual(plot_bool_for_item(ITEM_NAME_TO_ID["Liara T'Soni"]), 3943)
        self.assertEqual(plot_bool_for_item(ITEM_NAME_TO_ID["Tali'Zorah nar Rayya"]), 3944)
        self.assertEqual(plot_bool_for_item(ITEM_NAME_TO_ID["Feros Coordinates"]), 20002)
        self.assertIsNone(plot_bool_for_item(FRAGMENT_ITEM_ID))

    def test_received_squad_item_sets_inparty(self):
        bridge = FakeBridge(ints={2000: 0})
        sync_received_items(bridge, [SimpleNamespace(item=ITEM_NAME_TO_ID["Liara T'Soni"])])
        self.assertEqual(bridge.bool_writes, [(3943, True)])
        self.assertEqual(bridge.ints[2000], 1)

    def test_ilos_gate(self):
        fragment = SimpleNamespace(item=FRAGMENT_ITEM_ID)
        other = SimpleNamespace(item=ITEM_NAME_TO_ID["Feros Coordinates"])
        cases = [
            ("unknown requirement", [fragment] * 4, None, True, False),
            ("too few fragments", [fragment, other], 2, True, False),
            ("virmire not done", [fragment] * 2, 2, False, False),
            ("gate met", [fragment, other, fragment], 2, True, True),
        ]
        for name, items, required, virmire, opens in cases:
            with self.subTest(name):
                bridge = FakeBridge(bools={2509: virmire})
                self.assertEqual(sync_ilos_gate(bridge, items, required), opens)
                self.assertEqual(bridge.bool_writes, [(ILOS_OPEN_PLOT_BOOL, True)] if opens else [])

    def test_ilos_gate_does_not_rewrite_when_open(self):
        bridge = FakeBridge(bools={2509: True, ILOS_OPEN_PLOT_BOOL: True})
        self.assertFalse(sync_ilos_gate(bridge, [SimpleNamespace(item=FRAGMENT_ITEM_ID)], 1))
        self.assertEqual(bridge.bool_writes, [])


class TestMultiBoolPredicate(unittest.TestCase):
    def test_any_of_many_bools(self):
        predicate = parse_plot_predicate("bool 10 or 20 or 30")
        self.assertEqual(predicate.indices, (10, 20, 30))
        self.assertTrue(predicate.evaluate(FakeBridge(bools={30: True})))
        self.assertEqual(parse_plot_predicate("bool 3941 InParty.Turian (note)").indices, (3941,))
