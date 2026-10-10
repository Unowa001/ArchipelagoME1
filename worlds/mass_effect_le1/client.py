"""Archipelago client for Mass Effect Legendary Edition 1.

The client talks to LE1APBridge.asi over its local named pipe.  Pipe I/O is
kept behind :class:`BridgeConnection` so the game-facing behavior can be
tested without either LE1 or an Archipelago server.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
from dataclasses import dataclass
import logging
import random
import re
from typing import BinaryIO, Callable, Collection, Protocol, Sequence

import colorama

import Utils
from CommonClient import CommonContext, get_base_parser, gui_enabled, handle_url_arg, server_loop
from NetUtils import ClientStatus

from .data import FRAGMENT, ID_BASE, ITEM_NAME_TO_ID, ITEMS, LOCATIONS, LOCATION_NAME_TO_ID, UPGRADE
from .gear import GEAR_LINES, UPGRADE_ROWS
from .world import MassEffectLE1World

logger = logging.getLogger("ME1Client")

PIPE_NAME = r"\\.\pipe\LE1APBridge"
RECEIVED_INDEX_PLOT_INT = 2000
GOAL_PLOT_BOOL = 2511
VIRMIRE_DONE_PLOT_BOOL = 2509
ILOS_OPEN_PLOT_BOOL = 4103  # D5: set by the client once the fragment gate (and D9) is met
UNLOCK_CONTAINERS_PLOT_BOOL = 20190  # the bridge opens Decryption containers like plain ones while this is set
POLL_INTERVAL_SECONDS = 2.0


class BridgeError(Exception):
    """Base class for bridge transport and protocol failures."""


class GameNotReadyError(BridgeError):
    """The bridge is running, but LE1 has no world/save loaded yet."""


class BridgeProtocolError(BridgeError):
    """The bridge rejected a request or returned a malformed reply."""


PipeOpener = Callable[[str, str, int], BinaryIO]


class BridgeConnection:
    """Small reconnecting request/reply client for LE1APBridge's named pipe."""

    def __init__(self, pipe_name: str = PIPE_NAME, opener: PipeOpener = open) -> None:
        self.pipe_name = pipe_name
        self._opener = opener
        self._pipe: BinaryIO | None = None

    def close(self) -> None:
        if self._pipe is not None:
            with contextlib.suppress(OSError):
                self._pipe.close()
            self._pipe = None

    def _connect(self) -> BinaryIO:
        if self._pipe is None:
            self._pipe = self._opener(self.pipe_name, "r+b", 0)
        return self._pipe

    def request(self, request: str) -> str:
        """Send one ASCII request, reconnecting once after a transport failure."""
        if not request.isascii():
            raise ValueError("bridge requests must be ASCII")

        last_error: OSError | None = None
        for _attempt in range(2):
            try:
                pipe = self._connect()
                pipe.write(request.encode("ascii"))
                reply = pipe.read(512).decode("ascii")
                if not reply:
                    raise OSError("bridge closed the pipe without replying")
                return self._parse_reply(request, reply)
            except (OSError, UnicodeDecodeError) as error:
                last_error = error if isinstance(error, OSError) else OSError(str(error))
                self.close()

        raise BridgeError(f"bridge request failed after reconnect: {last_error}") from last_error

    @staticmethod
    def _parse_reply(request: str, reply: str) -> str:
        if reply == "ERR noworld":
            raise GameNotReadyError("LE1 has no world loaded")
        if reply == "ERR nosquad":
            raise GameNotReadyError("LE1 has no player squad yet")
        if reply.startswith("ERR "):
            raise BridgeProtocolError(f"{request!r}: {reply}")
        if reply == "OK":
            return ""
        if reply.startswith("OK "):
            return reply[3:]
        raise BridgeProtocolError(f"{request!r}: malformed reply {reply!r}")

    def ping(self) -> None:
        if self.request("PING") != "pong":
            raise BridgeProtocolError("PING returned an unexpected value")

    def get_bool(self, index: int) -> bool:
        value = self.request(f"GETB {index}")
        if value not in {"0", "1"}:
            raise BridgeProtocolError(f"GETB {index}: invalid bool {value!r}")
        return value == "1"

    def get_int(self, index: int) -> int:
        value = self.request(f"GETI {index}")
        try:
            return int(value)
        except ValueError as error:
            raise BridgeProtocolError(f"GETI {index}: invalid int {value!r}") from error

    def set_bool(self, index: int, value: bool) -> None:
        self.request(f"SETB {index} {int(value)}")

    def set_int(self, index: int, value: int) -> None:
        self.request(f"SETI {index} {value}")

    def give_item(self, item_row: int, sophistication: int, manufacturer_row: int) -> None:
        self.request(f"GIVE {item_row} {sophistication} {manufacturer_row}")

    def add_resource(self, resource: int, amount: int) -> None:
        self.request(f"RES {resource} {amount}")


class PlotReader(Protocol):
    def get_bool(self, index: int) -> bool: ...

    def get_int(self, index: int) -> int: ...


@dataclass(frozen=True)
class PlotPredicate:
    kind: str
    indices: tuple[int, ...]
    threshold: int | None = None

    def evaluate(self, bridge: PlotReader) -> bool:
        if self.kind == "bool":
            return any(bridge.get_bool(index) for index in self.indices)
        assert self.kind == "int" and self.threshold is not None
        return bridge.get_int(self.indices[0]) >= self.threshold


_BOOL_PREDICATE = re.compile(r"^bool\s+(\d+(?:\s+or\s+\d+)*)(?:\s+.*)?$", re.IGNORECASE)
_INT_PREDICATE = re.compile(r"^int\s+(\d+)\s*>=\s*(-?\d+)(?:\s+.*)?$", re.IGNORECASE)


def parse_plot_predicate(description: str | None) -> PlotPredicate | None:
    """Parse the supported leading forms used by ``LocationData.ot_plot``."""
    if not description:
        return None
    if match := _BOOL_PREDICATE.fullmatch(description.strip()):
        indices = tuple(int(value) for value in re.split(r"\s+or\s+", match.group(1), flags=re.IGNORECASE))
        return PlotPredicate("bool", indices)
    if match := _INT_PREDICATE.fullmatch(description.strip()):
        return PlotPredicate("int", (int(match.group(1)),), int(match.group(2)))
    return None


COORDINATE_ITEM_TO_PLOT_BOOL = {
    ID_BASE + item.offset: 20000 + item.offset - 0x10
    for item in ITEMS.values()
    if "Coordinates" in item.groups
}


# R10: a squadmate is recruited (selectable) when its InParty bool is set.
SQUAD_INPARTY_PLOT_BOOL = {
    "Kaidan Alenko": 3939,
    "Ashley Williams": 3940,
    "Garrus Vakarian": 3941,
    "Urdnot Wrex": 3942,
    "Liara T'Soni": 3943,
    "Tali'Zorah nar Rayya": 3944,
}
ITEM_TO_PLOT_BOOL = {
    **COORDINATE_ITEM_TO_PLOT_BOOL,
    **{ITEM_NAME_TO_ID[name]: plot_bool for name, plot_bool in SQUAD_INPARTY_PLOT_BOOL.items()},
}
FRAGMENT_ITEM_ID = ITEM_NAME_TO_ID[FRAGMENT]


def coordinate_bool_for_item(item_id: int) -> int | None:
    return COORDINATE_ITEM_TO_PLOT_BOOL.get(item_id)


def plot_bool_for_item(item_id: int) -> int | None:
    return ITEM_TO_PLOT_BOOL.get(item_id)


class ReceivedItem(Protocol):
    item: int


class ItemBridge(Protocol):
    def get_bool(self, index: int) -> bool: ...

    def get_int(self, index: int) -> int: ...

    def set_bool(self, index: int, value: bool) -> None: ...

    def set_int(self, index: int, value: int) -> None: ...

    def give_item(self, item_row: int, sophistication: int, manufacturer_row: int) -> None: ...

    def add_resource(self, resource: int, amount: int) -> None: ...


GEAR_BY_ITEM_ID = {ITEM_NAME_TO_ID[line.name]: line for line in GEAR_LINES}
UPGRADE_ITEM_ID = ITEM_NAME_TO_ID[UPGRADE]
# Bridge RES types: 0 credits, 1 medigel, 2 salvage (omni-gel), 3 grenades. Credits scale with the gear level.
CREDITS_PER_LEVEL = 500
RESOURCE_ITEMS = {
    ITEM_NAME_TO_ID["Credits"]: (0, None),
    ITEM_NAME_TO_ID["Omni-Gel"]: (2, 10),
    ITEM_NAME_TO_ID["Medi-Gel"]: (1, 3),
    ITEM_NAME_TO_ID["Grenades"]: (3, 2),
}
NO_MANUFACTURER = -1


def gear_level(gear_seen: int, gear_total: int) -> int:
    """Sophistication for the next gear delivery: I for the first gear line received, X for the last."""
    if gear_total <= 1:
        return 1
    return 1 + min(9, 9 * gear_seen // (gear_total - 1))


def upgrade_row(seed_name: str, index: int) -> int:
    """The Random Upgrade at received index `index`; the same on every replay of this seed."""
    return UPGRADE_ROWS[random.Random(f"{seed_name}:{index}").randrange(len(UPGRADE_ROWS))]


def apply_item(bridge: ItemBridge, item_id: int, index: int, gear_seen: int, gear_total: int, seed_name: str,
               log: logging.Logger = logger) -> None:
    """Deliver one received item to the game (plot flag, gear or resource)."""
    level = gear_level(gear_seen, gear_total)
    if (plot_bool := plot_bool_for_item(item_id)) is not None:
        bridge.set_bool(plot_bool, True)
    elif (line := GEAR_BY_ITEM_ID.get(item_id)) is not None:
        bridge.give_item(line.item_row, 10 if line.spectre else level, line.manufacturer_row)
    elif item_id == UPGRADE_ITEM_ID:
        bridge.give_item(upgrade_row(seed_name, index), level, NO_MANUFACTURER)
    elif (resource := RESOURCE_ITEMS.get(item_id)) is not None:
        kind, amount = resource
        bridge.add_resource(kind, amount if amount is not None else CREDITS_PER_LEVEL * level)
    else:
        log.info("Received unsupported item %s; skipping game write", item_id)


def sync_received_items(
    bridge: ItemBridge,
    received_items: Sequence[ReceivedItem],
    log: logging.Logger = logger,
    gear_total: int = 0,
    seed_name: str = "",
) -> int:
    """Apply items after the save's durable received index and return the new index.

    The index is written after every item, so a failure mid-way (e.g. a load screen) resumes at the first item not yet
    delivered. Gear levels depend only on the server's item order, so a replay (new game, older save) delivers the same
    items at the same levels."""
    saved_index = bridge.get_int(RECEIVED_INDEX_PLOT_INT)
    start_index = max(saved_index, 0)
    if saved_index < 0:
        log.warning("Save has negative AP received index %s; replaying from zero", saved_index)
    if start_index > len(received_items):
        log.warning(
            "Save AP received index %s is ahead of the server's %s items; leaving it unchanged",
            start_index,
            len(received_items),
        )
        return start_index

    gear_seen = sum(1 for item in received_items[:start_index] if item.item in GEAR_BY_ITEM_ID)
    for index in range(start_index, len(received_items)):
        item_id = received_items[index].item
        apply_item(bridge, item_id, index, gear_seen, gear_total, seed_name, log)
        if item_id in GEAR_BY_ITEM_ID:
            gear_seen += 1
        bridge.set_int(RECEIVED_INDEX_PLOT_INT, index + 1)
    return len(received_items)


def sync_ilos_gate(
    bridge: ItemBridge,
    received_items: Sequence[ReceivedItem],
    fragments_required: int | None,
) -> bool:
    """Open Ilos (D5, D9) once enough fragments arrived and Virmire is done; the server's list is authoritative."""
    if fragments_required is None:
        return False
    fragments = sum(1 for item in received_items if item.item == FRAGMENT_ITEM_ID)
    if fragments < fragments_required or not bridge.get_bool(VIRMIRE_DONE_PLOT_BOOL):
        return False
    if not bridge.get_bool(ILOS_OPEN_PLOT_BOOL):
        bridge.set_bool(ILOS_OPEN_PLOT_BOOL, True)
        return True
    return False


LOCATION_PREDICATES = {
    LOCATION_NAME_TO_ID[name]: predicate
    for name, location in LOCATIONS.items()
    if (predicate := parse_plot_predicate(location.ot_plot)) is not None
}
UNSUPPORTED_LOCATIONS = tuple(
    name for name, location in LOCATIONS.items() if parse_plot_predicate(location.ot_plot) is None
)


# Test run v2 (2026-10-09): the vanilla recruit transitions (Garrus 2006, Wrex 1998) set only InParty + InSquad, and
# the *_asks_to_join bools stay false on the clinic/Fist paths. Until the mod sets AP recruit flags (P8), these
# locations read InParty, which counts only while the client has not received that squadmate (it writes InParty then).
INPARTY_BOOL_TO_SQUAD_ITEM = {plot_bool: ITEM_NAME_TO_ID[name] for name, plot_bool in SQUAD_INPARTY_PLOT_BOOL.items()}


def evaluate_location_predicates(bridge: PlotReader, received_item_ids: Collection[int] = ()) -> set[int]:
    received = set(received_item_ids)
    return {
        location_id
        for location_id, predicate in LOCATION_PREDICATES.items()
        if not (predicate.kind == "bool" and len(predicate.indices) == 1
                and INPARTY_BOOL_TO_SQUAD_ITEM.get(predicate.indices[0]) in received)
        and predicate.evaluate(bridge)
    }


class ME1Context(CommonContext):
    game = MassEffectLE1World.game
    items_handling = 0b111
    gear_total = 0  # from slot data on Connected
    unlock_containers = False

    def __init__(
        self,
        server_address: str | None,
        password: str | None,
        bridge: BridgeConnection | None = None,
    ) -> None:
        self.bridge = bridge or BridgeConnection()
        self._bridge_ready: bool | None = None
        self.fragments_required: int | None = None
        super().__init__(server_address, password)
        for name in UNSUPPORTED_LOCATIONS:
            logger.info("Skipping location with unsupported plot predicate: %s", name)

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict) -> None:
        if cmd == "Connected":
            slot_data = args.get("slot_data", {})
            self.fragments_required = slot_data.get("fragments_required")
            self.gear_total = slot_data.get("gear_total", 0)
            self.unlock_containers = bool(slot_data.get("unlock_containers", False))

    def _server_ready(self) -> bool:
        return self.slot is not None and self.server is not None and not self.server.socket.closed

    def _read_game_state(self, server_ready: bool) -> tuple[set[int], bool]:
        self.bridge.ping()
        items: tuple = ()
        if server_ready:
            items = tuple(self.items_received)
            sync_received_items(self.bridge, items, gear_total=self.gear_total, seed_name=getattr(self, "seed_name", None) or "")
            if self.unlock_containers and not self.bridge.get_bool(UNLOCK_CONTAINERS_PLOT_BOOL):
                self.bridge.set_bool(UNLOCK_CONTAINERS_PLOT_BOOL, True)
                logger.info("Unlock Containers: Decryption containers now open like plain ones")
            if sync_ilos_gate(self.bridge, items, self.fragments_required):
                logger.info("Fragment gate met; Ilos opened")
        true_locations = evaluate_location_predicates(self.bridge, {item.item for item in items})
        goal_complete = self.bridge.get_bool(GOAL_PLOT_BOOL)
        return true_locations, goal_complete

    async def poll_game(self) -> None:
        # Without a connected slot, items_received is not authoritative and sends would be dropped.
        server_ready = self._server_ready()
        true_locations, goal_complete = await asyncio.to_thread(self._read_game_state, server_ready)
        if not server_ready:
            return

        new_locations = true_locations - self.checked_locations - self.locations_checked
        if self.server_locations:
            new_locations &= self.server_locations
        if new_locations:
            self.locations_checked.update(new_locations)
            await self.send_msgs([{"cmd": "LocationChecks", "locations": sorted(new_locations)}])
            logger.info("Sent %s new location check(s)", len(new_locations))

        if goal_complete and not self.finished_game:
            self.finished_game = True
            await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
            logger.info("Goal complete")

    async def bridge_loop(self) -> None:
        try:
            while not self.exit_event.is_set():
                try:
                    await self.poll_game()
                    if self._bridge_ready is not True:
                        logger.info("Connected to LE1APBridge with a game world loaded")
                    self._bridge_ready = True
                except GameNotReadyError:
                    if self._bridge_ready is not False:
                        logger.info("LE1APBridge is connected; waiting for a game world")
                    self._bridge_ready = False
                except BridgeError as error:
                    if self._bridge_ready is not False:
                        logger.warning("LE1APBridge unavailable: %s", error)
                    self._bridge_ready = False
                except OSError as error:
                    if self._bridge_ready is not False:
                        logger.warning("LE1APBridge pipe unavailable: %s", error)
                    self.bridge.close()
                    self._bridge_ready = False
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
        finally:
            self.bridge.close()


async def _main(args: argparse.Namespace) -> None:
    ctx = ME1Context(args.connect, args.password)
    ctx.auth = args.name
    ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
    bridge_task = asyncio.create_task(ctx.bridge_loop(), name="ME1 bridge loop")

    # get_base_parser only defines --nogui when stdout exists; the Launcher spawns clients without a console.
    if gui_enabled and not getattr(args, "nogui", False):
        ctx.run_gui()
    ctx.run_cli()

    try:
        await ctx.exit_event.wait()
    finally:
        bridge_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await bridge_task
        await ctx.shutdown()


def launch(*launch_args: str) -> None:
    parser = get_base_parser(description="Mass Effect Legendary Edition 1 Archipelago Client")
    parser.add_argument("--name", default=None, help="Slot name to connect as.")
    parser.add_argument("url", nargs="?", help="archipelago:// connection URL")
    args = handle_url_arg(parser.parse_args(launch_args or None), parser)

    Utils.init_logging("ME1Client", exception_logger="Client")
    colorama.just_fix_windows_console()
    try:
        asyncio.run(_main(args))
    finally:
        colorama.deinit()


if __name__ == "__main__":
    launch()
