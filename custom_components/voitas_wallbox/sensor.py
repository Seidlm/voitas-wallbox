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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Voitas Wallbox sensors."""
    coordinator: VoitasWallboxCoordinator = hass.data[DOMAIN][entry.entry_id]
    power_source = entry.data.get(CONF_POWER_SOURCE, POWER_SOURCE_MANUAL)
    power_value = entry.data.get(CONF_POWER_VALUE, 11.0)
    power_entity = entry.data.get(CONF_POWER_ENTITY, "")

    status_sensor = VoitasStatusSensor(coordinator, entry)
    power_sensor = VoitasPowerSensor(coordinator, entry, power_source, power_value, power_entity)
    energy_sensor = VoitasEnergySensor(coordinator, entry, power_sensor)

    async_add_entities([status_sensor, power_sensor, energy_sensor])


class VoitasStatusSensor(CoordinatorEntity[VoitasWallboxCoordinator], SensorEntity):
    """Sensor for wallbox status (idle/charging)."""

    _attr_has_entity_name = True
    _attr_name = "Status"
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Voitas Wallbox ({coordinator.host})",
            "manufacturer": "Voitas Innovations",
            "model": "V11",
        }

    @property
    def native_value(self):
        return self.coordinator.current_data.status

    @property
    def extra_state_attributes(self):
        d = self.coordinator.current_data
        return {
            "uuid": d.uuid,
            "max_power_w": d.max_power_w,
            "protocol_version": d.protocol_version,
        }

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
        self._power_source = power_source
        self._power_value = power_value
        self._power_entity = power_entity
        self._entity_power: float | None = None
        self._hass = coordinator.hass
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Voitas Wallbox ({coordinator.host})",
            "manufacturer": "Voitas Innovations",
            "model": "V11",
        }

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
            # Read current value immediately
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
        # Only return power when actually charging
        if self.coordinator.current_data.status != STATUS_CHARGING:
            return 0.0

        if self._power_source == POWER_SOURCE_ENTITY:
            return self._entity_power or 0.0
        else:
            return self._power_value

    @property
    def available(self):
        return self.coordinator.current_data.available


class VoitasEnergySensor(CoordinatorEntity[VoitasWallboxCoordinator], SensorEntity):
    """Sensor for total energy delivered (kWh) — calculated via time integration."""

    _attr_has_entity_name = True
    _attr_name = "Energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator, entry, power_sensor: VoitasPowerSensor):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_energy"
        self._power_sensor = power_sensor
        self._energy_kwh: float = 0.0
        self._last_update = dt_util.utcnow()
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Voitas Wallbox ({coordinator.host})",
            "manufacturer": "Voitas Innovations",
            "model": "V11",
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        now = dt_util.utcnow()
        elapsed_hours = (now - self._last_update).total_seconds() / 3600.0
        power_kw = self._power_sensor.native_value or 0.0
        self._energy_kwh += power_kw * elapsed_hours
        self._last_update = now
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self._energy_kwh, 4)

    @property
    def available(self):
        return self.coordinator.current_data.available
