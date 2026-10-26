"""AMI event listener and parking-slot state coordinator."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_HOST, CONF_PASSWORD, CONF_PARKINGLOT, CONF_PORT, CONF_SLOT_END,
    CONF_SLOT_START, CONF_USERNAME, DEFAULT_PARKINGLOT, DOMAIN, RECONNECT_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


def _parse_packet(raw: bytes) -> dict[str, str]:
    """Parse one AMI message into lowercase keys."""
    packet: dict[str, str] = {}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            packet[key.lower()] = value
    return packet


class AsteriskParkingCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Track parking space state from AMI."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        config = {**entry.data, **entry.options}
        self.host = config[CONF_HOST]
        self.port = int(config[CONF_PORT])
        self.username = config[CONF_USERNAME]
        self.password = config[CONF_PASSWORD]
        self.parkinglot = config.get(CONF_PARKINGLOT, DEFAULT_PARKINGLOT)
        start = int(config[CONF_SLOT_START])
        end = int(config[CONF_SLOT_END])
        self.slots = tuple(str(slot) for slot in range(start, end + 1))
        self.data = {
            slot: {"status": "unknown", "caller_id": None, "caller_id_name": None, "channel": None}
            for slot in self.slots
        }
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._stopped = False
        self._action_id = 0
        self._snapshot_complete = False
        self._snapshot_seen: set[str] = set()

    async def async_start(self) -> None:
        """Start background listener."""
        self._task = self.hass.async_create_task(self._connection_loop())

    async def async_stop(self) -> None:
        """Stop listener."""
        self._stopped = True
        if self._writer:
            self._writer.close()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _connection_loop(self) -> None:
        while not self._stopped:
            try:
                await self._listen_once()
            except asyncio.CancelledError:
                raise
            except (OSError, asyncio.TimeoutError, ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as err:
                _LOGGER.warning("AMI connection failed; retrying: %s", err)
            finally:
                self._writer = None
                self._snapshot_complete = False
                self._snapshot_seen.clear()
                for slot in self.slots:
                    self.data[slot] = {
                        "status": "unknown", "caller_id": None, "caller_id_name": None, "channel": None
                    }
                self.async_set_updated_data(self.data)
            if not self._stopped:
                await asyncio.sleep(RECONNECT_SECONDS)

    async def _listen_once(self) -> None:
        """Connect, log in, request snapshot, and consume events."""
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=8
        )
        self._writer = writer
        await asyncio.wait_for(reader.readline(), timeout=5)
        await self._send_action(
            writer, "Login", Username=self.username, Secret=self.password, Events="on"
        )
        await self._send_action(writer, "ParkingStatus", Parkinglot=self.parkinglot)
        while not self._stopped:
            packet = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=90)
            self._handle_packet(_parse_packet(packet))

    async def _send_action(
        self, writer: asyncio.StreamWriter, action: str, **fields: str
    ) -> None:
        """Send an AMI action."""
        self._action_id += 1
        lines = [f"Action: {action}", f"ActionID: parking_{self._action_id}"]
        lines.extend(f"{key}: {value}" for key, value in fields.items())
        writer.write(("\r\n".join(lines) + "\r\n\r\n").encode())
        await writer.drain()

    @callback
    def _handle_packet(self, packet: dict[str, str]) -> None:
        """Update slot state from AMI events."""
        event = packet.get("event", "").lower()
        if event == "parkedcall":
            if packet.get("parkinglot", self.parkinglot) != self.parkinglot:
                return
            slot = packet.get("parkingspace")
            if slot in self.data:
                self._snapshot_seen.add(slot)
                self.data[slot] = {
                    "status": "waiting",
                    "caller_id": packet.get("parkeecalleridnum") or packet.get("calleridnum"),
                    "caller_id_name": packet.get("parkeecalleridname") or packet.get("calleridname"),
                    "channel": packet.get("parkeechannel") or packet.get("channel"),
                }
                self.async_set_updated_data(self.data)
        elif event == "parkingstatuscomplete":
            if packet.get("parkinglot", self.parkinglot) != self.parkinglot:
                return
            self._snapshot_complete = True
            for slot in self.slots:
                if slot not in self._snapshot_seen:
                    self.data[slot] = {
                        "status": "free", "caller_id": None, "caller_id_name": None, "channel": None
                    }
            self.async_set_updated_data(self.data)
        elif event in {
            "unparkedcall", "parkedcallgiveup", "parkedcalltimeout",
            "parkedcallhangup",
        }:
            if packet.get("parkinglot", self.parkinglot) != self.parkinglot:
                return
            slot = packet.get("parkingspace")
            if slot in self.data:
                self.data[slot] = {
                    "status": "free", "caller_id": None, "caller_id_name": None, "channel": None
                }
                self.async_set_updated_data(self.data)
