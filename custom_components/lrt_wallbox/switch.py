"""Switch entity for Wallbox charging control."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from lrt_wallbox import WallboxError, WallboxNotFoundError

from .const import ATTR_CHARGING, ATTR_CHARGING_IS_ON
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
    """Set up the Wallbox switch entity."""
    coordinator = config_entry.runtime_data.coordinator
    async_add_entities([WallboxChargeSwitch(coordinator)])


class WallboxChargeSwitch(WallboxBaseEntity, SwitchEntity):
    """Switch to start/stop Wallbox charging."""

    _attr_translation_key = ATTR_CHARGING
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator: LrtWallboxCoordinator) -> None:
        """Initialize the Wallbox charging switch."""
        super().__init__(coordinator, ATTR_CHARGING)

    async def async_turn_on(self, **kwargs) -> None:
        """Start charging."""
        _LOGGER.debug("Starting charging")
        tags = await self.executor.call("rfid_get", priority=1)
        if not tags:
            raise HomeAssistantError(
                "No RFID tag enrolled; add one before starting a charge."
            )
        await self.executor.call("transaction_start", tags[0].tagId, priority=1)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Stop charging."""
        _LOGGER.debug("Stopping charging")
        try:
            await self.executor.call("transaction_stop", priority=1)
        except WallboxNotFoundError:
            _LOGGER.debug("No active transaction found to stop")
        except WallboxError as e:
            raise HomeAssistantError(f"Failed to stop charging: {e}") from e
        await self.coordinator.async_request_refresh()

    @property
    def is_on(self) -> bool:
        """Return True if charging is active."""
        data = self.coordinator.data or {}
        return bool(data.get(ATTR_CHARGING_IS_ON, False))

    @property
    def available(self) -> bool:
        """Available whenever the device is reachable.

        The switch's key (``charging``) is its identity, not a data field, so
        availability must not require it to be present in ``coordinator.data``.
        """
        return self.coordinator.last_update_success
