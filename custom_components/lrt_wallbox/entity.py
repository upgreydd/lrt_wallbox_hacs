"""Base entity classes for the LRT Wallbox integration."""

from __future__ import annotations

from homeassistant.const import ATTR_SERIAL_NUMBER
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_ESP_FW, DOMAIN
from .coordinator import LrtWallboxCoordinator


class WallboxBaseEntity(CoordinatorEntity[LrtWallboxCoordinator]):
    """Base class for all LRT Wallbox entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LrtWallboxCoordinator, key: str | None = None) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._key = key
        entry = coordinator.config_entry
        data = coordinator.data or {}
        if key is not None:
            self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="LRT Wallbox",
            manufacturer="LRT eMobility",
            model="Smart Vibe",
            serial_number=data.get(ATTR_SERIAL_NUMBER),
            sw_version=data.get(ATTR_ESP_FW),
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if self._key is None:
            return super().available
        return (
            super().available
            and self.coordinator.data is not None
            and self._key in self.coordinator.data
        )

    @property
    def executor(self):
        """Shortcut to the serialized device transport."""
        return self.coordinator.executor
