"""Wallbox sensor platform for Home Assistant."""

from __future__ import annotations

from typing import Any, Mapping

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_SERIAL_NUMBER,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_ATMEL_FW,
    ATTR_CHARGER_CURRENT_RATE,
    ATTR_CHARGER_SECONDS_SINCE_START,
    ATTR_CHARGER_STATUS,
    ATTR_ESP_FW,
    ATTR_LAST_5_TRANSACTIONS,
    ATTR_TRANSACTION_CURRENT_ENERGY,
)
from .coordinator import LrtWallboxCoordinator
from .entity import WallboxBaseEntity
from .models import LrtConfigEntry

PARALLEL_UPDATES = 0

# OCPP charge-point states as lowercase enum slugs. HA requires enum option and
# translation-state keys to match [a-z0-9-_]+, so the entity normalizes the raw
# device value (e.g. "Available") to its lowercase form.
CHARGER_STATE_OPTIONS = [
    "available",
    "preparing",
    "charging",
    "suspendedevse",
    "suspendedev",
    "finishing",
    "reserved",
    "unavailable",
    "faulted",
    "occupied",
]

METADATA_SENSOR_DEFINITIONS: dict[str, dict[str, Any]] = {
    ATTR_ATMEL_FW: {"translation_key": ATTR_ATMEL_FW, "icon": "mdi:chip"},
    ATTR_ESP_FW: {"translation_key": ATTR_ESP_FW, "icon": "mdi:cpu-32-bit"},
    ATTR_SERIAL_NUMBER: {
        "translation_key": ATTR_SERIAL_NUMBER,
        "icon": "mdi:information-outline",
    },
    ATTR_CHARGER_STATUS: {
        "translation_key": ATTR_CHARGER_STATUS,
        "icon": "mdi:ev-station",
        "device_class": SensorDeviceClass.ENUM,
    },
    ATTR_CHARGER_CURRENT_RATE: {
        "translation_key": ATTR_CHARGER_CURRENT_RATE,
        "icon": "mdi:flash-outline",
        "device_class": SensorDeviceClass.POWER,
        "unit_of_measurement": UnitOfPower.WATT,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    ATTR_CHARGER_SECONDS_SINCE_START: {
        "translation_key": ATTR_CHARGER_SECONDS_SINCE_START,
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "unit_of_measurement": UnitOfTime.SECONDS,
    },
    ATTR_TRANSACTION_CURRENT_ENERGY: {
        "translation_key": ATTR_TRANSACTION_CURRENT_ENERGY,
        "icon": "mdi:lightning-bolt",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        # Accumulates within a charging session and resets each session → TOTAL
        # (MEASUREMENT is invalid for the energy device class).
        "state_class": SensorStateClass.TOTAL,
    },
    ATTR_LAST_5_TRANSACTIONS: {
        "translation_key": ATTR_LAST_5_TRANSACTIONS,
        "icon": "mdi:history",
        "device_class": SensorDeviceClass.ENERGY,
        "unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        "state_class": SensorStateClass.TOTAL,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LrtConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wallbox sensors from a config entry."""
    coordinator = config_entry.runtime_data.coordinator
    async_add_entities(
        WallboxSensor(coordinator, key) for key in METADATA_SENSOR_DEFINITIONS
    )


class WallboxSensor(WallboxBaseEntity, SensorEntity):
    """Sensor for Wallbox metadata."""

    def __init__(self, coordinator: LrtWallboxCoordinator, key: str) -> None:
        """Initialize the Wallbox metadata sensor."""
        super().__init__(coordinator, key)
        definition = METADATA_SENSOR_DEFINITIONS[key]
        self._attr_icon = definition["icon"]
        self._attr_device_class = definition.get("device_class")
        self._attr_translation_key = definition["translation_key"]
        self._attr_native_unit_of_measurement = definition.get("unit_of_measurement")
        self._attr_state_class = definition.get("state_class")
        self._attr_entity_category = definition.get(
            "entity_category", EntityCategory.DIAGNOSTIC
        )
        if key == ATTR_CHARGER_STATUS:
            self._attr_options = CHARGER_STATE_OPTIONS

    @property
    def native_value(self) -> Any:
        """Return the value of the sensor."""
        data = self.coordinator.data or {}
        if self._key == ATTR_LAST_5_TRANSACTIONS:
            lst = data.get(self._key)
            lst = lst if isinstance(lst, list) else []
            first = lst[0] if lst else None
            return first.get("energy") if first else None
        if self._key == ATTR_CHARGER_STATUS:
            val = data.get(self._key)
            return val.lower() if isinstance(val, str) else None
        return data.get(self._key)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the transaction history for the last-5 sensor."""
        if self._key != ATTR_LAST_5_TRANSACTIONS:
            return None
        data = self.coordinator.data or {}
        lst = data.get(ATTR_LAST_5_TRANSACTIONS)
        lst = lst if isinstance(lst, list) else []
        if not lst:
            return None
        first = lst[0]
        return {
            "start_time": first.get("startTime"),
            "end_time": first.get("endTime"),
            "energy": first.get("energy"),
            "history": lst[1:5],
        }
