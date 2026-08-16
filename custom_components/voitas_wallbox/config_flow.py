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
    CONF_POWER_VALUE,
    CONF_POWER_ENTITY,
    DEFAULT_POWER_VALUE,
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

            try:
                socket.inet_aton(host)
            except socket.error:
                errors[CONF_HOST] = "invalid_host"
            else:
                ok = await _test_connection(host, port)
                if not ok:
                    errors["base"] = "cannot_connect"
                else:
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
        )

    async def async_step_power(self, user_input=None):
        """Configure fallback power value and optional linked entity together.

        The static value is always required (used when no entity is linked,
        or as fallback when the linked entity is unknown/unavailable). The
        entity is optional and takes priority whenever it reports a valid value.
        """
        if user_input is not None:
            await self.async_set_unique_id(self._host)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Voitas Wallbox ({self._host})",
                data={
                    CONF_HOST: self._host,
                    CONF_PORT: self._port,
                    CONF_POWER_VALUE: user_input.get(CONF_POWER_VALUE, DEFAULT_POWER_VALUE),
                    CONF_POWER_ENTITY: user_input.get(CONF_POWER_ENTITY, ""),
                },
            )

        return self.async_show_form(
            step_id="power",
            data_schema=vol.Schema({
                vol.Required(CONF_POWER_VALUE, default=DEFAULT_POWER_VALUE): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1.0, max=22.0, step=0.1, unit_of_measurement="kW"
                    )
                ),
                vol.Optional(CONF_POWER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="power",
                    )
                ),
            }),
        )

    @classmethod
    @callback
    def async_get_options_flow(cls, config_entry):
        return VoitasWallboxOptionsFlow(config_entry)


class VoitasWallboxOptionsFlow(config_entries.OptionsFlow):
    """Options flow — change fallback value / linked entity after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        super().__init__()
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Edit fallback power value and optional linked entity together."""
        current_value = self._config_entry.data.get(CONF_POWER_VALUE, DEFAULT_POWER_VALUE)
        current_entity = self._config_entry.data.get(CONF_POWER_ENTITY, "")

        if user_input is not None:
            return self.async_create_entry(data={
                **self._config_entry.data,
                CONF_POWER_VALUE: user_input.get(CONF_POWER_VALUE, DEFAULT_POWER_VALUE),
                CONF_POWER_ENTITY: user_input.get(CONF_POWER_ENTITY, ""),
            })

        schema = {
            vol.Required(CONF_POWER_VALUE, default=current_value): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1.0, max=22.0, step=0.1, unit_of_measurement="kW"
                )
            ),
        }
        if current_entity:
            schema[vol.Optional(CONF_POWER_ENTITY, default=current_entity)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            )
        else:
            schema[vol.Optional(CONF_POWER_ENTITY)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
        )
