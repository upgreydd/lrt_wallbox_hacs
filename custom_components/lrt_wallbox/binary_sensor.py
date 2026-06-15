"""Binary sensor for Wallbox network/setup/error status."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_ATMEL_ERROR,
    ATTR_CHARGING_IS_ON,
    ATTR_NETWORK_STATUS_ETHERNET,
    ATTR_NETWORK_STATUS_WLAN,
    ATTR_SETUP_STATUS_AMBIENT_LIGHT,
    ATTR_SETUP_STATUS_MAX_CHARGING_POWER,
    ATTR_SETUP_STATUS_NETWORK,
)
from .coordinator import LrtWallboxCoordinator
from .entity import WallboxBaseEntity
from .models import LrtConfigEntry

PARALLEL_UPDATES = 0

SENSOR_DEFINITIONS: dict[str, dict[str, Any]] = {
    ATTR_NETWORK_STATUS_WLAN: {
        "translation_key": ATTR_NETWORK_STATUS_WLAN,
        "icon": "mdi:wifi",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
    },
    ATTR_NETWORK_STATUS_ETHERNET: {
        "translation_key": ATTR_NETWORK_STATUS_ETHERNET,
        "icon": "mdi:ethernet",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
    },
    ATTR_SETUP_STATUS_NETWORK: {
        "translation_key": ATTR_SETUP_STATUS_NETWORK,
        "icon": "mdi:network-outline",
        "device_class": BinarySensorDeviceClass.POWER,
    },
    ATTR_SETUP_STATUS_AMBIENT_LIGHT: {
        "translation_key": ATTR_SETUP_STATUS_AMBIENT_LIGHT,
        "icon": "mdi:brightness-6",
        "device_class": BinarySensorDeviceClass.POWER,
    },
    ATTR_SETUP_STATUS_MAX_CHARGING_POWER: {
        "translation_key": ATTR_SETUP_STATUS_MAX_CHARGING_POWER,
        "icon": "mdi:flash",
        "device_class": BinarySensorDeviceClass.POWER,
    },
    ATTR_ATMEL_ERROR: {
        "translation_key": ATTR_ATMEL_ERROR,
        "icon": "mdi:alert-circle-outline",
        "device_class": BinarySensorDeviceClass.PROBLEM,
    },
    ATTR_CHARGING_IS_ON: {
        "translation_key": ATTR_CHARGING_IS_ON,
        "icon": "mdi:ev-station",
        "device_class": BinarySensorDeviceClass.BATTERY_CHARGING,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LrtConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = config_entry.runtime_data.coordinator
    async_add_entities(
        StatusBinarySensor(coordinator, key) for key in SENSOR_DEFINITIONS
    )


class StatusBinarySensor(WallboxBaseEntity, BinarySensorEntity):
    """Sensor for Wallbox network/setup/error status."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: LrtWallboxCoordinator, key: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, key)
        definition = SENSOR_DEFINITIONS[key]
        self._attr_icon = definition.get("icon")
        self._attr_translation_key = definition["translation_key"]
        self._attr_device_class = definition["device_class"]

    @property
    def is_on(self) -> bool | None:
        """Return the binary state."""
        data = self.coordinator.data or {}
        return data.get(self._key)
