import collections
import logging
from types import SimpleNamespace
import unittest

from ..client import (
    SHOP_TRANSITIONS,
    BridgeConnection,
    BridgeProtocolError,
    GameNotReadyError,
    ID_BASE,
    ME1CommandProcessor,
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
    deliver_notices,
    notice_lines,
    notice_text,
    INFINITE_SPRINT_PLOT_BOOL,
    SHOP_SLOTS_PLOT_INT,
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
        self.notes = []
        self.fail_note = False
        self.map = "BIOA_NOR00"
        self.presses = 0
        self.v10 = True
        self.v11 = True
        self.boxes = []
        self.fail_box = False
        self.shop_labels = {}
        self.shop_clears = 0

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

    def note(self, text):
        if self.fail_note:
            raise GameNotReadyError("load screen")
        self.notes.append(text)

    def version(self):
        return 11 if self.v11 else 10

    def shop_item(self, transition, name, description):
        if not self.v11:
            raise AssertionError("SHOPITEM sent to a bridge older than v11")
        self.shop_labels[transition] = (name, description)

    def shop_clear(self):
        self.shop_clears += 1
        self.shop_labels.clear()

    def message_box(self, lines):
        if not self.v11:
            raise AssertionError("MSGBOX sent to a bridge older than v11")
        if self.fail_box:
            raise GameNotReadyError("load screen")
        self.boxes.append(list(lines))

    def run_transition(self, transition):
        if not self.v10:
            raise BridgeProtocolError(f"'XST {transition}': ERR badrequest")
        self.transitions = getattr(self, "transitions", []) + [transition]
        self.bools[transition] = True  # AP transitions 20xxx set the bool of the same number

    def map_name(self):
        if not self.v10:
            raise BridgeProtocolError("'MAP': ERR badrequest")
        return self.map

    def key_presses(self):
        if not self.v10:
            raise BridgeProtocolError("'KEYS': ERR badrequest")
        presses, self.presses = self.presses, 0
        return presses


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

    def test_recruits_read_the_mod_flags_not_inparty(self):
        garrus, wrex = LOCATION_NAME_TO_ID["Citadel: Recruit Garrus"], LOCATION_NAME_TO_ID["Citadel: Recruit Wrex"]
        # InParty is also written by item delivery, so it must not count as a recruitment.
        self.assertFalse({garrus, wrex} & evaluate_location_predicates(FakeBridge(bools={3941: True, 3942: True})))
        # The mod's recruit transitions 20101/20102 set these flags.
        self.assertTrue({garrus, wrex} <= evaluate_location_predicates(FakeBridge(bools={20101: True, 20102: True})))


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
        ctx.infinite_sprint, ctx.notices, ctx.notices_enabled, ctx._fragments_noticed = False, collections.deque(), True, None
        ctx.sends_pending = collections.deque()
        ctx.locations_info = {}
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
        ctx.infinite_sprint, ctx.notices, ctx.notices_enabled, ctx._fragments_noticed = False, collections.deque(), True, None
        ctx.sends_pending = collections.deque()
        ctx.locations_info = {}
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


class TestNotices(unittest.TestCase):
    def test_notice_text_is_ascii_single_line(self):
        self.assertEqual(notice_text("Received Tali'Zorah from José"), "Received Tali'Zorah from Jose")
        self.assertEqual(notice_text("a\nb\tc"), "a b c")
        self.assertEqual(notice_text("x" * 500), "x" * 500)  # never cut: notice_lines wraps it
        self.assertEqual(notice_text("☃"), "?")

    def test_notice_lines_wrap_without_dropping_text(self):
        text = "Received Aldrin Labs Onyx Light Armor (Turian) from Nic_Elden"
        lines = notice_lines(text)
        self.assertTrue(all(len(line) <= 18 for line in lines))
        self.assertEqual(" ".join(lines), text)
        self.assertEqual(notice_lines("Found Medi-Gel"), ["Found Medi-Gel"])
        self.assertEqual(notice_lines("Hint: " + "x" * 40), ["Hint:", "x" * 18, "x" * 18, "x" * 4])
        self.assertEqual(notice_lines("☃"), ["?"])

    def test_deliver_keeps_the_rest_queued(self):
        bridge = FakeBridge()
        notices = collections.deque(f"n{i}" for i in range(5))
        deliver_notices(bridge, notices, limit=3)
        self.assertEqual(bridge.notes, ["n0", "n1", "n2"])
        self.assertEqual(list(notices), ["n3", "n4"])
        bridge.fail_note = True
        with self.assertRaises(GameNotReadyError):
            deliver_notices(bridge, notices)
        self.assertEqual(list(notices), ["n3", "n4"])  # nothing lost on a load screen

    def test_item_send_texts(self):
        ctx = object.__new__(ME1Context)
        ctx.slot, ctx.slot_info = 1, {}
        ctx.player_names = {1: "Shepard", 2: "Link"}
        ctx.item_names = SimpleNamespace(lookup_in_slot=lambda code, slot: f"item{code}@{slot}")
        self.assertEqual(ctx.item_send_notice(SimpleNamespace(item=5, player=2), 1), "Received item5@1 from Link")
        self.assertEqual(ctx.item_send_notice(SimpleNamespace(item=5, player=1), 2), "Sent item5@2 to Link")
        self.assertEqual(ctx.item_send_notice(SimpleNamespace(item=5, player=1), 1), "Found item5@1")


class TestNoticeLevels(unittest.TestCase):
    def make_ctx(self):
        ctx = object.__new__(ME1Context)
        ctx.slot, ctx.slot_info = 1, {}
        ctx.player_names = {1: "Shepard", 2: "Link"}
        ctx.item_names = SimpleNamespace(lookup_in_slot=lambda code, slot: f"item{code}")
        ctx.location_names = SimpleNamespace(lookup_in_slot=lambda code, slot: f"loc{code}")
        ctx.notices, ctx.sends_pending = collections.deque(), collections.deque()
        ctx.locations_info = {}
        ctx.notices_enabled, ctx.notice_level = True, "all"
        return ctx

    @staticmethod
    def send(ctx, receiving, sender, item=5):
        ME1Context.notice_for_print(ctx, {"type": "ItemSend", "receiving": receiving,
                                          "item": SimpleNamespace(item=item, player=sender)})

    def test_sends_are_batched_per_poll(self):
        ctx = self.make_ctx()
        self.send(ctx, 2, 1)
        self.send(ctx, 2, 1)
        self.send(ctx, 1, 2, item=7)
        self.assertEqual(list(ctx.notices), ["Received item7", "from Link"])  # items for this slot: right away
        ctx.notices.clear()
        ctx._flush_sends()
        self.assertEqual(list(ctx.notices), ["Sent 2 items"])
        ctx.notices.clear()
        self.send(ctx, 2, 1)
        ctx._flush_sends()
        self.assertEqual(list(ctx.notices), ["Sent item5 to Link"])
        self.assertFalse(ctx.sends_pending)

    def test_levels(self):
        ctx = self.make_ctx()
        ctx.notify("Normandy: 3 checks in logic", important=False)
        ctx.notify("Found Medi-Gel")
        self.assertEqual(list(ctx.notices), ["Normandy: 3 checks", "in logic", "Found Medi-Gel"])
        ctx.notices.clear()
        ctx.notice_level = "important"
        ctx.notify("Normandy: 3 checks in logic", important=False)
        self.send(ctx, 2, 1)
        ctx.notify("Found Medi-Gel")
        self.assertEqual((list(ctx.notices), list(ctx.sends_pending)), (["Found Medi-Gel"], []))
        ctx.notices.clear()
        ctx.notice_level = "off"
        ctx.notify("Found Medi-Gel")
        self.assertFalse(ctx.notices)

    def test_notices_command(self):
        ctx = self.make_ctx()
        ctx.notices.append("old")
        processor = ME1Context.command_processor(ctx)
        outputs = []
        processor.output = outputs.append
        self.assertTrue(processor._cmd_notices("important"))
        self.assertEqual(ctx.notice_level, "important")
        self.assertEqual(list(ctx.notices), ["old"])
        self.assertTrue(processor._cmd_notices("OFF"))
        self.assertEqual((ctx.notice_level, ctx.notices_reset), ("off", True))  # cleared by the next poll
        self.assertFalse(processor._cmd_notices("loud"))
        self.assertEqual(ctx.notice_level, "off")
        self.assertTrue(processor._cmd_notices())
        self.assertEqual(outputs[-1], "In-game notices: off")


class TestQualityOfLifeSync(unittest.TestCase):
    def make_ctx(self, bridge, items, infinite_sprint):
        ctx = object.__new__(ME1Context)
        ctx.bridge = bridge
        ctx.items_received = items
        ctx.slot = 1
        ctx.server = SimpleNamespace(socket=SimpleNamespace(closed=False))
        ctx.fragments_required = 4
        ctx.gear_total = 0
        ctx.unlock_containers = False
        ctx.infinite_sprint, ctx.notices, ctx.notices_enabled, ctx._fragments_noticed = infinite_sprint, collections.deque(), True, None
        ctx.sends_pending = collections.deque()
        ctx.locations_info = {}
        return ctx

    def test_sprint_option_is_mirrored_both_ways(self):
        bridge = FakeBridge(ints={2000: 0})
        self.make_ctx(bridge, [], True)._read_game_state(True)
        self.assertTrue(bridge.bools[INFINITE_SPRINT_PLOT_BOOL])
        self.make_ctx(bridge, [], False)._read_game_state(True)
        self.assertFalse(bridge.bools[INFINITE_SPRINT_PLOT_BOOL])

    def test_shop_slot_count_is_written_once_connected(self):
        bridge = FakeBridge(ints={2000: 0, SHOP_SLOTS_PLOT_INT: 0})
        ctx = self.make_ctx(bridge, [], False)
        ctx._read_game_state(True)
        self.assertEqual(bridge.ints[SHOP_SLOTS_PLOT_INT], 0)  # no slot data yet: the mod shows every slot
        ctx.shop_slots = 3
        ctx._read_game_state(True)
        self.assertEqual(bridge.ints[SHOP_SLOTS_PLOT_INT], 4)

    def test_fragment_notice_only_for_new_fragments(self):
        bridge = FakeBridge(ints={2000: 0})
        items = [SimpleNamespace(item=FRAGMENT_ITEM_ID)]
        ctx = self.make_ctx(bridge, items, False)
        ctx._read_game_state(True)  # first poll after connecting: baseline, no notice
        self.assertEqual(bridge.notes, [])
        items.append(SimpleNamespace(item=FRAGMENT_ITEM_ID))
        ctx._read_game_state(True)
        self.assertEqual(bridge.notes, ["Fragments: 2/4"])


class TestInGameTracker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ..tracker import Tracker
        cls.tracker = Tracker({"required_squad_size": 2})

    def make_ctx(self, bridge):
        ctx = object.__new__(ME1Context)
        ctx.bridge = bridge
        ctx.items_received = []
        ctx.slot = 1
        ctx.server = SimpleNamespace(socket=SimpleNamespace(closed=False))
        ctx.fragments_required = 4
        ctx.gear_total = 0
        ctx.unlock_containers = False
        ctx.infinite_sprint, ctx.notices, ctx.notices_enabled, ctx._fragments_noticed = False, collections.deque(), True, None
        ctx.sends_pending = collections.deque()
        ctx.locations_info = {}
        ctx.tracker = self.tracker
        ctx.missing_locations = set(LOCATION_NAME_TO_ID.values())
        ctx.locations_checked = set()
        return ctx

    def test_landing_notice_once_per_new_area(self):
        bridge = FakeBridge(ints={2000: 0})
        ctx = self.make_ctx(bridge)
        ctx._tracker_notices([])
        landed = len(ctx.notices)
        self.assertRegex(" ".join(ctx.notices), r"^Normandy: \d+ checks? in logic")  # one notice, wrapped into lines
        ctx._tracker_notices([])
        self.assertEqual(len(ctx.notices), landed)  # same area: nothing new
        bridge.map = "BIOA_WAR00"
        ctx._tracker_notices([])
        self.assertRegex(" ".join(list(ctx.notices)[landed:]), r"^Feros: 0 checks in logic, \d+ locked$")

    def test_hotkey_shows_the_summary_box(self):
        bridge = FakeBridge(ints={2000: 0})
        ctx = self.make_ctx(bridge)
        ctx._last_area = "Normandy"
        bridge.presses = 1
        ctx._tracker_notices([])
        ctx._deliver_summary()
        self.assertEqual(len(bridge.boxes), 1)
        box = bridge.boxes[0]
        self.assertEqual(box[0], "Archipelago")
        self.assertTrue(box[1].startswith("In logic: "))
        self.assertTrue(any(line.startswith("Locked: ") for line in box))
        self.assertNotIn("planets)", " ".join(box))  # the box lists every uncharted planet in logic
        self.assertFalse(ctx.notices)

    def test_summary_box_waits_for_a_load_screen(self):
        bridge = FakeBridge(ints={2000: 0})
        ctx = self.make_ctx(bridge)
        ctx._last_area = "Normandy"
        bridge.presses, bridge.fail_box = 1, True
        ctx._tracker_notices([])
        ctx._deliver_summary()
        self.assertFalse(bridge.boxes)
        bridge.fail_box = False
        ctx._deliver_summary()
        self.assertEqual(len(bridge.boxes), 1)

    def test_older_bridge_sends_the_summary_as_notices(self):
        bridge = FakeBridge(ints={2000: 0})
        bridge.v11 = False
        ctx = self.make_ctx(bridge)
        ctx._last_area = "Normandy"
        bridge.presses = 1
        ctx._tracker_notices([])
        ctx._deliver_summary()
        self.assertFalse(bridge.boxes)
        text = " ".join(ctx.notices)
        self.assertTrue(text.startswith("In logic: "))
        self.assertIn(" Locked: ", text)
        self.assertTrue(all(len(line) <= 18 for line in ctx.notices))

    def test_notices_command_clears_on_the_poll_thread(self):
        bridge = FakeBridge(ints={2000: 0})
        ctx = self.make_ctx(bridge)
        ctx.notices.extend(["a", "b"])
        ctx.sends_pending.append("Sent x to y")
        processor = object.__new__(ME1CommandProcessor)
        processor.ctx = ctx
        processor.output = lambda text: None
        processor._cmd_notices("off")
        self.assertEqual(list(ctx.notices), ["a", "b"])  # untouched until the poll
        ctx._read_game_state(True)
        self.assertFalse(ctx.notices)
        self.assertFalse(ctx.sends_pending)
        self.assertFalse(ctx.notices_reset)

    def test_summary_too_long_for_the_box_goes_to_notices_whole(self):
        bridge = FakeBridge()
        ctx = self.make_ctx(bridge)
        ctx.summary_pending = (["Archipelago"] + ["x" * 90] * 100, ["x" * 90] * 100)
        ctx._deliver_summary()
        self.assertFalse(bridge.boxes)
        self.assertEqual("".join(ctx.notices), "x" * 9000)  # nothing cut

    def test_version_of_an_older_bridge(self):
        bridge = BridgeConnection(opener=lambda *args: FakePipe(b"ERR badrequest"))
        self.assertEqual(bridge.version(), 10)
        bridge = BridgeConnection(opener=lambda *args: FakePipe(b"OK 11"))
        self.assertEqual(bridge.version(), 11)

    def test_message_box_request(self):
        pipe = FakePipe(b"OK")
        bridge = BridgeConnection(opener=lambda *args: pipe)
        bridge.message_box(["Archipelago", "In logic: Feros 3", "Caf\u00e9\tok"])
        self.assertEqual(pipe.writes[-1], b"MSGBOX 0 Archipelago\nIn logic: Feros 3\nCafe ok")

    def test_older_bridge_turns_the_tracker_off(self):
        bridge = FakeBridge(ints={2000: 0})
        bridge.v10 = False
        ctx = self.make_ctx(bridge)
        ctx.tracker_enabled = True
        ctx._read_game_state(True)
        self.assertFalse(ctx.tracker_enabled)

    def test_hint_notice(self):
        ctx = object.__new__(ME1Context)
        ctx.slot = 1
        ctx.slot_info = {}
        ctx.player_names = {1: "Shepard", 2: "Link"}
        ctx.item_names = SimpleNamespace(lookup_in_slot=lambda code, slot: f"item{code}")
        ctx.location_names = SimpleNamespace(lookup_in_slot=lambda code, slot: f"loc{code}")
        self.assertEqual(ctx.hint_notice(SimpleNamespace(item=5, location=9, player=2), 1), "Hint: your item5 is at Link's loc9")
        self.assertEqual(ctx.hint_notice(SimpleNamespace(item=5, location=9, player=1), 1), "Hint: your item5 is at loc9")
        self.assertEqual(ctx.hint_notice(SimpleNamespace(item=5, location=9, player=1), 2), "Hint: Link's item5 is at your loc9")


class TestJournalSync(unittest.TestCase):
    def make_ctx(self, bridge, items=(), tracker=None):
        ctx = object.__new__(ME1Context)
        ctx.bridge = bridge
        ctx.items_received = list(items)
        ctx.fragments_required = 4
        ctx.mako_shuffled = True
        ctx.tracker = tracker
        ctx.missing_locations = set(LOCATION_NAME_TO_ID.values())
        ctx.locations_checked = set()
        return ctx

    def test_values_and_activation_through_the_transition(self):
        bridge = FakeBridge(ints={2000: 0})
        ctx = self.make_ctx(bridge, [SimpleNamespace(item=FRAGMENT_ITEM_ID)] * 2)
        ctx._sync_journal(ctx.items_received)
        self.assertEqual((bridge.ints[2002], bridge.ints[2003]), (2, 4))
        self.assertFalse(bridge.bools.get(20193, False))  # Mako shuffled and not received
        self.assertEqual(bridge.transitions, [20192])
        writes = len(bridge.int_writes) + len(bridge.bool_writes)
        ctx._sync_journal(ctx.items_received)
        self.assertEqual(len(bridge.int_writes) + len(bridge.bool_writes), writes)  # nothing changed: no writes
        self.assertEqual(bridge.transitions, [20192])
        bridge.ints[2002] = 0  # an older save was loaded
        ctx._sync_journal(ctx.items_received)
        self.assertEqual(bridge.ints[2002], 2)

    def test_older_bridge_sets_the_bool(self):
        bridge = FakeBridge(ints={2000: 0})
        bridge.v10 = False
        self.make_ctx(bridge)._sync_journal([])
        self.assertTrue(bridge.bools[20192])

    def test_regions_in_logic(self):
        from ..tracker import Tracker
        bridge = FakeBridge(ints={2000: 0})
        ctx = self.make_ctx(bridge, tracker=Tracker({"required_squad_size": 2, "mako_shuffled": True}))
        ctx._sync_journal([])
        self.assertTrue(bridge.bools[20800])  # Normandy (data.Region index 0)
        self.assertFalse(bridge.bools.get(20804, False))  # Feros: no coordinates yet
        self.assertTrue(bridge.bools[20900 + 3])  # galaxy-map marker area 3 (Feros): locked checks
        self.assertFalse(bridge.bools.get(20850 + 3, False))  # ... none in logic
        self.assertTrue(bridge.bools[20850 + 0])  # Citadel: checks in logic

    def test_marker_areas_match_the_mod(self):
        from ..tracker import MARKER_AREAS, UNCHARTED_PLANETS
        self.assertEqual(len(MARKER_AREAS), 40)  # tools/le1mod/Markers.cs Areas
        self.assertEqual(MARKER_AREAS[:8], ("Citadel", "Eden Prime", "Therum", "Feros", "Noveria", "Virmire", "Asteroid X57", "Ilos"))
        self.assertEqual(MARKER_AREAS[33], "Chasca")
        self.assertEqual(set(MARKER_AREAS[8:]), set(UNCHARTED_PLANETS))


class TestShopLabels(unittest.TestCase):
    def make_ctx(self, bridge):
        ctx = object.__new__(ME1Context)
        ctx.bridge = bridge
        ctx.slot = 1
        ctx.slot_info = {}
        ctx.player_names = {1: "Shepard", 2: "Link"}
        ctx.item_names = SimpleNamespace(lookup_in_slot=lambda code, slot: f"item{code}")
        ctx.locations_info = {}
        return ctx

    def test_every_shop_slot_maps_to_its_transition(self):
        self.assertEqual(sorted(SHOP_TRANSITIONS.values()), list(range(20700, 20750)))
        self.assertEqual(SHOP_TRANSITIONS[LOCATION_NAME_TO_ID["Normandy: Requisitions Officer Slot 1"]], 20700)
        self.assertEqual(SHOP_TRANSITIONS[LOCATION_NAME_TO_ID["Virmire: Salarian Camp Slot 5"]], 20749)

    def test_labels_for_scouted_slots(self):
        bridge = FakeBridge()
        ctx = self.make_ctx(bridge)
        own = LOCATION_NAME_TO_ID["Normandy: Requisitions Officer Slot 1"]
        other = LOCATION_NAME_TO_ID["Feros: Zhu's Hope Merchant Slot 2"]
        ctx.locations_info = {own: SimpleNamespace(item=7, location=own, player=1, flags=1),
                              other: SimpleNamespace(item=9, location=other, player=2, flags=0)}
        ctx._send_shop_labels()
        self.assertTrue(ctx.shop_labels_sent)
        self.assertEqual(bridge.shop_clears, 1)
        self.assertEqual(bridge.shop_labels, {
            20700: ("item7", "Archipelago item for you: item7. Progression."),
            SHOP_TRANSITIONS[other]: ("Link's item9", "Archipelago item for Link: item9. Filler."),
        })

    def test_older_bridge_gets_no_labels(self):
        bridge = FakeBridge()
        bridge.v11 = False
        ctx = self.make_ctx(bridge)
        loc = LOCATION_NAME_TO_ID["Normandy: Requisitions Officer Slot 1"]
        ctx.locations_info = {loc: SimpleNamespace(item=7, location=loc, player=1, flags=2)}
        ctx._send_shop_labels()
        self.assertTrue(ctx.shop_labels_sent)
        self.assertFalse(bridge.shop_labels)

    def test_shop_item_request(self):
        pipe = FakePipe(b"OK")
        bridge = BridgeConnection(opener=lambda *args: pipe)
        bridge.shop_item(20703, "Link's Hook|shot", "Archipelago item for Link: Hookshot. Useful.")
        self.assertEqual(pipe.writes[-1], b"SHOPITEM 20703 Link's Hook/shot|Archipelago item for Link: Hookshot. Useful.")
