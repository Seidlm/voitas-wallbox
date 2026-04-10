"""Binary sensor for Voitas Wallbox."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, STATUS_CHARGING
from .coordinator import VoitasWallboxCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Voitas Wallbox binary sensors."""
    coordinator: VoitasWallboxCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([VoitasChargingBinarySensor(coordinator, entry)])


class VoitasChargingBinarySensor(CoordinatorEntity[VoitasWallboxCoordinator], BinarySensorEntity):
    """Binary sensor: is the wallbox currently charging?"""

    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_has_entity_name = True
    _attr_name = "Charging"

    def __init__(self, coordinator: VoitasWallboxCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_charging"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": f"Voitas Wallbox ({coordinator.host})",
            "manufacturer": "Voitas Innovations",
            "model": "V11",
        }

    @property
    def is_on(self) -> bool:
        return self.coordinator.current_data.status == STATUS_CHARGING

    @property
    def available(self) -> bool:
        return self.coordinator.current_data.available
