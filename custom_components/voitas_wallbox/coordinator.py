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
    """Parse a UDP broadcast packet from the Voitas Wallbox.

    Format: WALLBOX-LD <proto> <uuid> <status> <f4> <max_power_w> <min_current_ma> <interval_ms>
    """
    try:
        text = data.decode("ascii").strip()
        parts = text.split(" ")
        if len(parts) < 6 or parts[0] != "WALLBOX-LD":
            return None
        return VoitasData(
            status=parts[3],
            uuid=parts[2],
            max_power_w=int(parts[5]),
            protocol_version=int(parts[1]),
            raw=text,
            available=True,
            last_seen=dt_util.utcnow(),
        )
    except Exception:
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
        loop = asyncio.get_event_loop()
        try:
            self._transport, _ = await loop.create_datagram_endpoint(
                lambda: _VoitasUDPProtocol(self._on_packet),
                local_addr=("0.0.0.0", self.port),
                allow_broadcast=True,
            )
            _LOGGER.info("Voitas Wallbox: listening on UDP port %s", self.port)
        except OSError as err:
            _LOGGER.error("Failed to bind UDP port %s: %s", self.port, err)

    async def async_stop(self) -> None:
        if self._timeout_task:
            self._timeout_task.cancel()
        if self._transport:
            self._transport.close()
            self._transport = None

    def _on_packet(self, data: bytes, addr: tuple) -> None:
        host_ip = addr[0]
        if self.host and host_ip != self.host:
            return

        parsed = parse_packet(data)
        if parsed is None:
            return

        # Carry over last_session from previous data
        parsed.last_session = self._data.last_session

        # Track charging session start/end
        prev_status = self._data.status
        new_status = parsed.status

        if prev_status != "charging" and new_status == "charging":
            # Session started
            self._session_start = dt_util.utcnow()
            self._session_energy_kwh = 0.0
            _LOGGER.debug("Voitas: charging session started")

        elif prev_status == "charging" and new_status != "charging":
            # Session ended → save summary
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

        _LOGGER.debug("Voitas packet from %s: %s", host_ip, parsed.raw)
        self._data = parsed

        # Reset availability timeout
        if self._timeout_task:
            self._timeout_task.cancel()
        self._timeout_task = asyncio.ensure_future(self._availability_timeout())

        self.async_set_updated_data(parsed)

    async def _availability_timeout(self) -> None:
        """Mark unavailable if no packet received within timeout."""
        await asyncio.sleep(AVAILABILITY_TIMEOUT)
        _LOGGER.warning("Voitas Wallbox: no packet for %ss → unavailable", AVAILABILITY_TIMEOUT)
        self._data = VoitasData(
            available=False,
            last_session=self._data.last_session,
        )
        self.async_set_updated_data(self._data)


class _VoitasUDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, callback) -> None:
        self._callback = callback

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self._callback(data, addr)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.warning("Voitas UDP error: %s", exc)
