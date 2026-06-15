"""Number entity for controlling the maximum current limit."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_MAX_CURRENT, CONF_MAX_LOAD
from .coordinator import LrtWallboxCoordinator
from .entity import WallboxBaseEntity
from .models import LrtConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1
MIN_CURRENT = 6


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LrtConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wallbox number entities from a config entry."""
    coordinator = config_entry.runtime_data.coordinator
    max_load = config_entry.options.get(
        CONF_MAX_LOAD, config_entry.data.get(CONF_MAX_LOAD, 16)
    )
    async_add_entities([WallboxLoadLimitNumber(coordinator, max_load)])


class WallboxLoadLimitNumber(WallboxBaseEntity, NumberEntity):
    """Representation of a Wallbox max load number entity."""

    _attr_translation_key = ATTR_MAX_CURRENT
    _attr_icon = "mdi:current-ac"
    _attr_native_unit_of_measurement = "A"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1

    def __init__(self, coordinator: LrtWallboxCoordinator, max_load: int) -> None:
        """Initialize the Wallbox max load number entity."""
        super().__init__(coordinator, ATTR_MAX_CURRENT)
        self._attr_native_min_value = MIN_CURRENT
        self._attr_native_max_value = max_load

    async def async_set_native_value(self, value: float) -> None:
        """Set the load limit to the given value."""
        _LOGGER.debug("Setting max current to %s A", value)
        try:
            await self.executor.call("config_load_set", int(value), priority=1, timeout=15)
        except TimeoutError:
            _LOGGER.warning("config_load_set timed out; will refresh state anyway")
        finally:
            await self.coordinator.async_request_refresh()

    @property
    def native_value(self) -> float | None:
        """Return the current load limit value."""
        data = self.coordinator.data or {}
        value = data.get(ATTR_MAX_CURRENT)
        return float(value) if value is not None else None
