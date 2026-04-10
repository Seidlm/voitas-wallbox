"""DataUpdateCoordinator for Voitas Wallbox."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, STATUS_IDLE

_LOGGER = logging.getLogger(__name__)

BROADCAST_TIMEOUT = 5.0  # seconds to wait for a UDP packet


@dataclass
class VoitasData:
    """Parsed data from the Voitas Wallbox UDP broadcast."""
    status: str = STATUS_IDLE
    uuid: str = ""
    max_power_w: int = 0
    protocol_version: int = 3
    raw: str = ""
    available: bool = False


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
        )
    except Exception:
        return None


class VoitasWallboxCoordinator(DataUpdateCoordinator[VoitasData]):
    """Coordinator that listens for UDP broadcasts from the Voitas Wallbox."""

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
        )
        self.host = host
        self.port = port
        self._transport = None
        self._data = VoitasData()
        self._future: asyncio.Future | None = None

    @property
    def current_data(self) -> VoitasData:
        """Return current wallbox data."""
        return self._data

    async def _async_update_data(self) -> VoitasData:
        """Fetch data — for push-based UDP we just return the latest."""
        return self._data

    async def async_start(self) -> None:
        """Start listening for UDP broadcasts."""
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
        """Stop UDP listener."""
        if self._transport:
            self._transport.close()
            self._transport = None

    def _on_packet(self, data: bytes, addr: tuple) -> None:
        """Handle an incoming UDP packet."""
        host_ip = addr[0]
        if self.host and host_ip != self.host:
            return  # ignore packets from other devices

        parsed = parse_packet(data)
        if parsed is None:
            return

        _LOGGER.debug("Voitas packet from %s: %s", host_ip, parsed.raw)
        self._data = parsed
        self.async_set_updated_data(parsed)


class _VoitasUDPProtocol(asyncio.DatagramProtocol):
    """asyncio UDP protocol handler."""

    def __init__(self, callback) -> None:
        self._callback = callback

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self._callback(data, addr)

    def error_received(self, exc: Exception) -> None:
        _LOGGER.warning("Voitas UDP error: %s", exc)
