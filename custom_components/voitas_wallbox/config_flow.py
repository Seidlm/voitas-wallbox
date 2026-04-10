"""Config flow for Voitas Wallbox integration."""
from __future__ import annotations

import socket
import asyncio
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    DEFAULT_PORT,
    CONF_HOST,
    CONF_PORT,
    CONF_POWER_SOURCE,
    CONF_POWER_VALUE,
    CONF_POWER_ENTITY,
    POWER_SOURCE_MANUAL,
    POWER_SOURCE_ENTITY,
)


async def _test_connection(host: str, port: int) -> bool:
    """Try to receive a UDP broadcast from the wallbox."""
    loop = asyncio.get_event_loop()
    future = loop.create_future()

    class _TestProtocol(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            if not future.done() and addr[0] == host:
                future.set_result(data.decode("ascii", errors="ignore"))

        def error_received(self, exc):
            if not future.done():
                future.set_exception(exc)

    transport = None
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _TestProtocol(),
            local_addr=("0.0.0.0", port),
            allow_broadcast=True,
        )
        result = await asyncio.wait_for(future, timeout=8.0)
        return result.startswith("WALLBOX-LD")
    except (asyncio.TimeoutError, OSError):
        return False
    finally:
        if transport:
            transport.close()


class VoitasWallboxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Voitas Wallbox."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

            # Validate IP
            try:
                socket.inet_aton(host)
            except socket.error:
                errors[CONF_HOST] = "invalid_host"
            else:
                # Test connection
                ok = await _test_connection(host, port)
                if not ok:
                    errors["base"] = "cannot_connect"
                else:
                    # Store host/port, move to power config
                    self._host = host
                    self._port = port
                    return await self.async_step_power()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default="192.168.1.149"): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            }),
            errors=errors,
            description_placeholders={"port": str(DEFAULT_PORT)},
        )

    async def async_step_power(self, user_input=None):
        errors = {}

        if user_input is not None:
            source = user_input[CONF_POWER_SOURCE]
            data = {
                CONF_HOST: self._host,
                CONF_PORT: self._port,
                CONF_POWER_SOURCE: source,
            }
            if source == POWER_SOURCE_MANUAL:
                data[CONF_POWER_VALUE] = user_input.get(CONF_POWER_VALUE, 11.0)
            else:
                data[CONF_POWER_ENTITY] = user_input.get(CONF_POWER_ENTITY, "")

            await self.async_set_unique_id(self._host)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Voitas Wallbox ({self._host})",
                data=data,
            )

        return self.async_show_form(
            step_id="power",
            data_schema=vol.Schema({
                vol.Required(CONF_POWER_SOURCE, default=POWER_SOURCE_MANUAL): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=[
                        selector.SelectOptionDict(value=POWER_SOURCE_MANUAL, label="Manuell (kW eingeben)"),
                        selector.SelectOptionDict(value=POWER_SOURCE_ENTITY, label="HA Entity (z.B. Audi Sensor)"),
                    ])
                ),
                vol.Optional(CONF_POWER_VALUE, default=11.0): vol.Coerce(float),
                vol.Optional(CONF_POWER_ENTITY, default=""): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="power",
                    )
                ),
            }),
            errors=errors,
        )
