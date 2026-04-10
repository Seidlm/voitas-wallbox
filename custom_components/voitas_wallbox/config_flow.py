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
        """Step 1 of power config: choose source."""
        if user_input is not None:
            self._power_source = user_input[CONF_POWER_SOURCE]
            if self._power_source == POWER_SOURCE_MANUAL:
                return await self.async_step_power_manual()
            else:
                return await self.async_step_power_entity()

        return self.async_show_form(
            step_id="power",
            data_schema=vol.Schema({
                vol.Required(CONF_POWER_SOURCE, default=POWER_SOURCE_MANUAL): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=[
                        selector.SelectOptionDict(value=POWER_SOURCE_MANUAL, label="Manuell (kW eingeben)"),
                        selector.SelectOptionDict(value=POWER_SOURCE_ENTITY, label="HA Entity (z.B. Audi Sensor)"),
                    ])
                ),
            }),
        )

    async def async_step_power_manual(self, user_input=None):
        """Enter fixed kW value."""
        if user_input is not None:
            await self.async_set_unique_id(self._host)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Voitas Wallbox ({self._host})",
                data={
                    CONF_HOST: self._host,
                    CONF_PORT: self._port,
                    CONF_POWER_SOURCE: POWER_SOURCE_MANUAL,
                    CONF_POWER_VALUE: user_input.get(CONF_POWER_VALUE, 11.0),
                },
            )

        return self.async_show_form(
            step_id="power_manual",
            data_schema=vol.Schema({
                vol.Required(CONF_POWER_VALUE, default=11.0): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1.0, max=22.0, step=0.1, unit_of_measurement="kW"
                    )
                ),
            }),
        )

    async def async_step_power_entity(self, user_input=None):
        """Select HA entity for charging power."""
        errors = {}

        if user_input is not None:
            if not user_input.get(CONF_POWER_ENTITY):
                errors[CONF_POWER_ENTITY] = "entity_required"
            else:
                await self.async_set_unique_id(self._host)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Voitas Wallbox ({self._host})",
                    data={
                        CONF_HOST: self._host,
                        CONF_PORT: self._port,
                        CONF_POWER_SOURCE: POWER_SOURCE_ENTITY,
                        CONF_POWER_ENTITY: user_input[CONF_POWER_ENTITY],
                    },
                )

        return self.async_show_form(
            step_id="power_entity",
            data_schema=vol.Schema({
                vol.Required(CONF_POWER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="power",
                    )
                ),
            }),
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_options_flow(cls, config_entry):
        return VoitasWallboxOptionsFlow(config_entry)


class VoitasWallboxOptionsFlow(config_entries.OptionsFlow):
    """Options flow — change power source after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        super().__init__()
        self._config_entry = config_entry
        self._power_source = config_entry.data.get(CONF_POWER_SOURCE, POWER_SOURCE_MANUAL)

    async def async_step_init(self, user_input=None):
        """Choose power source."""
        if user_input is not None:
            self._power_source = user_input[CONF_POWER_SOURCE]
            if self._power_source == POWER_SOURCE_MANUAL:
                return await self.async_step_manual()
            else:
                return await self.async_step_entity()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_POWER_SOURCE, default=self._power_source): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=[
                        selector.SelectOptionDict(value=POWER_SOURCE_MANUAL, label="Manuell (kW eingeben)"),
                        selector.SelectOptionDict(value=POWER_SOURCE_ENTITY, label="HA Entity (z.B. Audi Sensor)"),
                    ])
                ),
            }),
        )

    async def async_step_manual(self, user_input=None):
        current = self._config_entry.data.get(CONF_POWER_VALUE, 11.0)

        if user_input is not None:
            return self.async_create_entry(data={
                **self._config_entry.data,
                CONF_POWER_SOURCE: POWER_SOURCE_MANUAL,
                CONF_POWER_VALUE: user_input[CONF_POWER_VALUE],
            })

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({
                vol.Required(CONF_POWER_VALUE, default=current): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1.0, max=22.0, step=0.1, unit_of_measurement="kW"
                    )
                ),
            }),
        )

    async def async_step_entity(self, user_input=None):
        errors = {}
        current = self._config_entry.data.get(CONF_POWER_ENTITY, "")

        if user_input is not None:
            if not user_input.get(CONF_POWER_ENTITY):
                errors[CONF_POWER_ENTITY] = "entity_required"
            else:
                return self.async_create_entry(data={
                    **self._config_entry.data,
                    CONF_POWER_SOURCE: POWER_SOURCE_ENTITY,
                    CONF_POWER_ENTITY: user_input[CONF_POWER_ENTITY],
                })

        return self.async_show_form(
            step_id="entity",
            data_schema=vol.Schema({
                vol.Required(CONF_POWER_ENTITY, default=current): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                        device_class="power",
                    )
                ),
            }),
            errors=errors,
        )
