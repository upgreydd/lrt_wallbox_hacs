"""Wallbox button entities."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_RESTART_WALLBOX
from .coordinator import LrtWallboxCoordinator
from .entity import WallboxBaseEntity
from .models import LrtConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LrtConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Wallbox button entity."""
    coordinator = config_entry.runtime_data.coordinator
    async_add_entities([RestartWallboxButton(coordinator)])


class RestartWallboxButton(WallboxBaseEntity, ButtonEntity):
    """Button to restart the Wallbox."""

    _attr_translation_key = ATTR_RESTART_WALLBOX
    _attr_icon = "mdi:restart-alert"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: LrtWallboxCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator, ATTR_RESTART_WALLBOX)

    async def async_press(self) -> None:
        """Handle the button press."""
        # util_restart frequently drops the connection as the device reboots;
        # the executor already treats that timeout as success.
        await self.executor.call("util_restart", priority=1)

    @property
    def available(self) -> bool:
        """Return True if the button is available."""
        return self.coordinator.last_update_success
