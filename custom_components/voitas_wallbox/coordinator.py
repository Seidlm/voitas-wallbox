"""DataUpdateCoordinator for Voitas Wallbox."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import homeassistant.util.dt as dt_util

from .const import DOMAIN, STATUS_IDLE

_LOGGER = logging.getLogger(__name__)

AVAILABILITY_TIMEOUT = 30.0  # seconds without packet → unavailable
MAX_UDP_PACKET_SIZE = 512    # bytes — reject oversized packets
MAX_POWER_W = 100_000        # 100kW sanity cap
MAX_PROTOCOL_VERSION = 99


@dataclass
class LastSession:
    """Summary of the last completed charging session."""
    start: datetime | None = None
    end: datetime | None = None
    duration_min: float = 0.0
    energy_kwh: float = 0.0


@dataclass
class VoitasData:
    """Parsed data from the Voitas Wallbox UDP broadcast."""
    status: str = STATUS_IDLE
    uuid: str = ""
    max_power_w: int = 0
    protocol_version: int = 3
    raw: str = ""
    available: bool = False
    last_seen: datetime | None = None
    last_session: LastSession = field(default_factory=LastSession)


def parse_packet(data: bytes) -> VoitasData | None:
    """Parse a UDP broadcast packet — with input validation.

    Format: WALLBOX-LD <proto> <uuid> <status> <f4> <max_power_w> <min_current_ma> <interval_ms>
    """
    # Fix #5: Reject oversized packets
    if len(data) > MAX_UDP_PACKET_SIZE:
        _LOGGER.warning("Voitas: oversized UDP packet (%d bytes), ignoring", len(data))
        return None
    try:
        text = data.decode("ascii").strip()
        parts = text.split(" ")
        if len(parts) < 6 or parts[0] != "WALLBOX-LD":
            return None

        # Fix #6: Bounds-check on numeric fields
        proto = int(parts[1])
        if not (0 <= proto <= MAX_PROTOCOL_VERSION):
            return None

        max_power = int(parts[5])
        if not (0 <= max_power <= MAX_POWER_W):
            return None

        # Validate UUID format loosely
        uuid = parts[2]
        if len(uuid) > 64:
            return None

        # Validate status is a known string
        status = parts[3].lower()
        if len(status) > 32:
            return None

        return VoitasData(
            status=status,
            uuid=uuid,
            max_power_w=max_power,
            protocol_version=proto,
            raw=text,
            available=True,
            last_seen=dt_util.utcnow(),
        )
    except (ValueError, UnicodeDecodeError):
        return None
    except Exception as err:
        _LOGGER.debug("Voitas: unexpected parse error: %s", err)
        return None


class VoitasWallboxCoordinator(DataUpdateCoordinator[VoitasData]):
    """Coordinator that listens for UDP broadcasts from the Voitas Wallbox."""

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.host = host
        self.port = port
        self._transport = None
        self._data = VoitasData()
        self._timeout_task: asyncio.Task | None = None
        self._timeout_task_id: int = 0  # Fix #2: Guard against stale tasks
        self._session_start: datetime | None = None
        self._session_energy_kwh: float = 0.0

    @property
    def current_data(self) -> VoitasData:
        return self._data

    def update_session_energy(self, kwh: float) -> None:
        """Called by EnergySensor to track current session energy."""
        self._session_energy_kwh = kwh

    async def _async_update_data(self) -> VoitasData:
        return self._data

    async def async_start(self) -> None:
        """Start listening for UDP broadcasts."""
        try:
            # Fix #4: use hass.loop instead of asyncio.get_event_loop()
            self._transport, _ = await self.hass.loop.create_datagram_endpoint(
                lambda: _VoitasUDPProtocol(self._on_packet),
                local_addr=("0.0.0.0", self.port),
                allow_broadcast=True,
            )
            _LOGGER.info("Voitas Wallbox: listening on UDP port %s", self.port)
        except OSError as err:
            _LOGGER.error("Failed to bind UDP port %s: %s", self.port, err)

    async def async_stop(self) -> None:
        """Stop UDP listener and clean up tasks."""
        # Fix #1: proper cleanup on unload
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass
        self._timeout_task = None

        if self._transport:
            self._transport.close()
            self._transport = None

    def _on_packet(self, data: bytes, addr: tuple) -> None:
        """Handle an incoming UDP packet (called from asyncio event loop)."""
        host_ip = addr[0]
        if self.host and host_ip != self.host:
            return

        parsed = parse_packet(data)
        if parsed is None:
            return

        # Carry over last_session from previous data
        parsed.last_session = self._data.last_session

        # Track charging session transitions
        prev_status = self._data.status
        new_status = parsed.status

        if prev_status != "charging" and new_status == "charging":
            self._session_start = dt_util.utcnow()
            self._session_energy_kwh = 0.0
            _LOGGER.debug("Voitas: charging session started")

        elif prev_status == "charging" and new_status != "charging":
            if self._session_start:
                end = dt_util.utcnow()
                duration = (end - self._session_start).total_seconds() / 60
                parsed.last_session = LastSession(
                    start=self._session_start,
                    end=end,
                    duration_min=round(duration, 1),
                    energy_kwh=round(self._session_energy_kwh, 3),
                )
                _LOGGER.debug(
                    "Voitas: session ended — %.1f min, %.3f kWh",
                    duration, self._session_energy_kwh,
                )
                self._session_start = None
                self._session_energy_kwh = 0.0

        # Fix #8: on reboot/reconnect, reset stale charging state
        if not self._data.available and new_status != "charging":
            self._session_start = None

        _LOGGER.debug("Voitas packet from %s: %s", host_ip, parsed.raw)
        self._data = parsed

        # Fix #1 + #2: use hass.async_create_task + stale-task guard
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()

        self._timeout_task_id += 1
        task_id = self._timeout_task_id

        # Fix #4: hass.async_create_task instead of asyncio.ensure_future
        self._timeout_task = self.hass.async_create_task(
            self._availability_timeout(task_id)
        )

        self.async_set_updated_data(parsed)

    async def _availability_timeout(self, task_id: int) -> None:
        """Mark unavailable if no packet received within timeout.

        Fix #2: task_id guard prevents stale tasks from firing.
        """
        await asyncio.sleep(AVAILABILITY_TIMEOUT)

        # Only fire if this is still the current timeout task
        if task_id != self._timeout_task_id:
            return

        _LOGGER.warning(
            "Voitas Wallbox: no packet for %ss → unavailable", AVAILABILITY_TIMEOUT
        )
        self._data = VoitasData(
            available=False,
            last_session=self._data.last_session,
        )
        self.async_set_updated_data(self._data)


class _VoitasUDPProtocol(asyncio.DatagramProtocol):
    """asyncio UDP protocol handler."""

    def __init__(self, callback) -> None:
        self._callback = callback

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self._callback(data, addr)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.warning("Voitas UDP error: %s", exc)
