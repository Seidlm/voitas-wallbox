"""Sensors for Voitas Wallbox."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from .const import (
    DOMAIN,
    CONF_POWER_SOURCE,
    CONF_POWER_VALUE,
    CONF_POWER_ENTITY,
    POWER_SOURCE_MANUAL,
    POWER_SOURCE_ENTITY,
    STATUS_CHARGING,
)
from .coordinator import VoitasWallboxCoordinator


def _device_info(coordinator, entry):
    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": f"Voitas Wallbox ({coordinator.host})",
        "manufacturer": "Voitas Innovations",
        "model": "V11",
        "serial_number": coordinator.current_data.uuid or None,
    }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: VoitasWallboxCoordinator = hass.data[DOMAIN][entry.entry_id]
    power_source = entry.data.get(CONF_POWER_SOURCE, POWER_SOURCE_MANUAL)
    power_value = entry.data.get(CONF_POWER_VALUE, 11.0)
    power_entity = entry.data.get(CONF_POWER_ENTITY, "")

    status_sensor = VoitasStatusSensor(coordinator, entry)
    power_sensor = VoitasPowerSensor(coordinator, entry, power_source, power_value, power_entity)
    energy_sensor = VoitasEnergySensor(coordinator, entry, power_sensor)
    duration_sensor = VoitasSessionDurationSensor(coordinator, entry)
    max_power_sensor = VoitasMaxPowerSensor(coordinator, entry)
    diagnostic_sensor = VoitasDiagnosticSensor(coordinator, entry)

    async_add_entities([
        status_sensor,
        power_sensor,
        energy_sensor,
        duration_sensor,
        max_power_sensor,
        diagnostic_sensor,
    ])


class VoitasStatusSensor(CoordinatorEntity[VoitasWallboxCoordinator], SensorEntity):
    """Sensor for wallbox status (idle/charging)."""

    _attr_has_entity_name = True
    _attr_name = "Status"
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._entry = entry

    @property
    def device_info(self):
        return _device_info(self.coordinator, self._entry)

    @property
    def native_value(self):
        return self.coordinator.current_data.status

    @property
    def extra_state_attributes(self):
        d = self.coordinator.current_data
        ls = d.last_session
        attrs = {
            "uuid": d.uuid,
            "max_power_w": d.max_power_w,
            "protocol_version": d.protocol_version,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        }
        if ls and ls.end:
            attrs["last_session_duration_min"] = ls.duration_min
            attrs["last_session_energy_kwh"] = ls.energy_kwh
            attrs["last_session_start"] = ls.start.isoformat() if ls.start else None
            attrs["last_session_end"] = ls.end.isoformat() if ls.end else None
        return attrs

    @property
    def available(self):
        return self.coordinator.current_data.available


class VoitasPowerSensor(CoordinatorEntity[VoitasWallboxCoordinator], SensorEntity):
    """Sensor for current charging power in kW."""

    _attr_has_entity_name = True
    _attr_name = "Charging Power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, coordinator, entry, power_source, power_value, power_entity):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_power"
        self._entry = entry
        self._power_source = power_source
        self._power_value = power_value
        self._power_entity = power_entity
        self._entity_power: float | None = None

    @property
    def device_info(self):
        return _device_info(self.coordinator, self._entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._power_source == POWER_SOURCE_ENTITY and self._power_entity:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    [self._power_entity],
                    self._handle_entity_state_change,
                )
            )
            state = self.hass.states.get(self._power_entity)
            if state and state.state not in ("unknown", "unavailable"):
                try:
                    self._entity_power = float(state.state)
                except ValueError:
                    pass

    @callback
    def _handle_entity_state_change(self, event) -> None:
        new_state = event.data.get("new_state")
        if new_state and new_state.state not in ("unknown", "unavailable"):
            try:
                self._entity_power = float(new_state.state)
                self.async_write_ha_state()
            except ValueError:
                pass

    @property
    def native_value(self) -> float:
        if self.coordinator.current_data.status != STATUS_CHARGING:
            return 0.0
        if self._power_source == POWER_SOURCE_ENTITY:
            return self._entity_power or 0.0
        return self._power_value

    @property
    def available(self):
        return self.coordinator.current_data.available


class VoitasEnergySensor(CoordinatorEntity[VoitasWallboxCoordinator], SensorEntity, RestoreEntity):
    """Sensor for total energy delivered (kWh) — calculated via time integration.

    Uses TOTAL_INCREASING so HA Energy Dashboard can track daily/monthly consumption.
    Value persists across HA restarts via RestoreEntity.
    """

    _attr_has_entity_name = True
    _attr_name = "Energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator, entry, power_sensor: VoitasPowerSensor):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_energy"
        self._entry = entry
        self._power_sensor = power_sensor
        self._energy_kwh: float = 0.0
        self._last_update = dt_util.utcnow()

    @property
    def device_info(self):
        return _device_info(self.coordinator, self._entry)

    async def async_added_to_hass(self) -> None:
        """Restore last known energy value after HA restart."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._energy_kwh = float(last_state.state)
            except (ValueError, TypeError):
                self._energy_kwh = 0.0
        self._last_update = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        now = dt_util.utcnow()
        elapsed_hours = (now - self._last_update).total_seconds() / 3600.0
        power_kw = self._power_sensor.native_value or 0.0
        if power_kw > 0:
            self._energy_kwh += power_kw * elapsed_hours
        self._last_update = now
        self.coordinator.update_session_energy(self._energy_kwh)
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self._energy_kwh, 4)

    @property
    def available(self):
        return self.coordinator.current_data.available


class VoitasSessionDurationSensor(CoordinatorEntity[VoitasWallboxCoordinator], SensorEntity):
    """Sensor for current charging session duration in minutes."""

    _attr_has_entity_name = True
    _attr_name = "Session Duration"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "min"
    _attr_icon = "mdi:timer"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_session_duration"
        self._entry = entry
        self._session_start: dt_util.dt.datetime | None = None

    @property
    def device_info(self):
        return _device_info(self.coordinator, self._entry)

    @callback
    def _handle_coordinator_update(self) -> None:
        status = self.coordinator.current_data.status
        if status == STATUS_CHARGING:
            if self._session_start is None:
                self._session_start = dt_util.utcnow()
        else:
            self._session_start = None
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        if self._session_start is None:
            return 0
        elapsed = (dt_util.utcnow() - self._session_start).total_seconds() / 60
        return round(elapsed, 1)

    @property
    def extra_state_attributes(self):
        return {
            "session_start": self._session_start.isoformat() if self._session_start else None,
        }

    @property
    def available(self):
        return self.coordinator.current_data.available


class VoitasMaxPowerSensor(CoordinatorEntity[VoitasWallboxCoordinator], SensorEntity):
    """Sensor for wallbox maximum power capacity."""

    _attr_has_entity_name = True
    _attr_name = "Max Power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_icon = "mdi:flash"
    _attr_entity_registry_enabled_default = False  # hidden by default, enable if needed

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_max_power"
        self._entry = entry

    @property
    def device_info(self):
        return _device_info(self.coordinator, self._entry)

    @property
    def native_value(self) -> float:
        return round(self.coordinator.current_data.max_power_w / 1000, 1)

    @property
    def available(self):
        return self.coordinator.current_data.available


class VoitasDiagnosticSensor(CoordinatorEntity[VoitasWallboxCoordinator], SensorEntity):
    """Diagnostic sensor showing last raw packet and packet stats."""

    _attr_has_entity_name = True
    _attr_name = "Last Packet"
    _attr_icon = "mdi:wifi"
    _attr_entity_registry_enabled_default = False  # hidden by default
    _attr_entity_category = "diagnostic"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_diagnostic"
        self._entry = entry
        self._packet_count: int = 0
        self._last_packet_time: dt_util.dt.datetime | None = None

    @property
    def device_info(self):
        return _device_info(self.coordinator, self._entry)

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.current_data.available:
            self._packet_count += 1
            self._last_packet_time = dt_util.utcnow()
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        d = self.coordinator.current_data
        return d.last_seen.isoformat() if d.last_seen else "never"

    @property
    def extra_state_attributes(self):
        d = self.coordinator.current_data
        return {
            "raw_packet": d.raw,
            "packets_received": self._packet_count,
            "uuid": d.uuid,
            "protocol_version": d.protocol_version,
            "available": d.available,
        }

    @property
    def available(self):
        return True  # always visible, even when box is offline
