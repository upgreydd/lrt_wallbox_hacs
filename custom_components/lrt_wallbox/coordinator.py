"""DataUpdateCoordinator for the LRT Wallbox integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_SERIAL_NUMBER
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from lrt_wallbox import WallboxAuthError, WallboxError, WallboxPermissionError

from .const import (
    ATTR_ATMEL_ERROR,
    ATTR_ATMEL_FW,
    ATTR_CHARGER_CURRENT_RATE,
    ATTR_CHARGER_SECONDS_SINCE_START,
    ATTR_CHARGER_STATUS,
    ATTR_CHARGING_IS_ON,
    ATTR_ESP_FW,
    ATTR_LAST_5_TRANSACTIONS,
    ATTR_MAX_CURRENT,
    ATTR_NETWORK_STATUS_ETHERNET,
    ATTR_NETWORK_STATUS_WLAN,
    ATTR_SETUP_STATUS_AMBIENT_LIGHT,
    ATTR_SETUP_STATUS_MAX_CHARGING_POWER,
    ATTR_SETUP_STATUS_NETWORK,
    ATTR_TRANSACTION_CURRENT_ENERGY,
)
from .helpers import WallboxClientExecutor, get_last_5_transactions

_LOGGER = logging.getLogger(__name__)


class LrtWallboxCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the wallbox and exposes a single merged state dict via ``data``."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        executor: WallboxClientExecutor,
        update_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="LRT Wallbox Status",
            config_entry=config_entry,
            update_interval=timedelta(seconds=update_interval),
        )
        self.executor = executor
        # Static, set-once device metadata (serial, firmware, setup flags). These
        # are merged into every update so entities read everything from `data`.
        self._static: dict[str, Any] = {}

    async def async_init_static(self) -> None:
        """Fetch the immutable device metadata once, before the first refresh."""
        serial = await self.executor.call("info_serial_get")
        firmwares = await self.executor.call("info_firmwares_get")
        setup_status = await self.executor.call("setup_get")

        self._static = {
            ATTR_SERIAL_NUMBER: serial.serialNumber,
            ATTR_ESP_FW: f"{firmwares.esp['major']}.{firmwares.esp['minor']}.{firmwares.esp['patch']}",
            ATTR_ATMEL_FW: (
                f"{firmwares.atmel['major']}.{firmwares.atmel['minor']}."
                f"{firmwares.atmel['revision']}.{firmwares.atmel['buildNumber']}"
            ),
            # Raw device flags: True == that part of setup is complete. Stored
            # once and never re-inverted (the previous code flipped these on
            # every poll, which made the binary sensors oscillate).
            ATTR_SETUP_STATUS_NETWORK: bool(setup_status.network),
            ATTR_SETUP_STATUS_AMBIENT_LIGHT: bool(setup_status.ambientLight),
            ATTR_SETUP_STATUS_MAX_CHARGING_POWER: bool(setup_status.maxChargingPower),
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the live status and merge it with the static metadata."""
        try:
            load_get = await self.executor.call("config_load_get", priority=10)
            transaction_status = await self.executor.call("transaction_get", priority=10)
            is_error = await self.executor.call("atmel_error_get", priority=10)
            network_status = await self.executor.call("config_network_status", priority=10)
            transaction_log = await self.executor.call("transaction_log_get", priority=10)
        except (WallboxAuthError, WallboxPermissionError) as err:
            # Credentials/authorization problem → ask the user to re-auth.
            raise ConfigEntryAuthFailed(str(err)) from err
        except (WallboxError, TimeoutError, OSError) as err:
            # Transient/communication problem → coordinator marks entities
            # unavailable and logs once (and once again on recovery).
            raise UpdateFailed(f"Error communicating with wallbox: {err}") from err

        last_5 = get_last_5_transactions(transaction_log)

        return {
            **self._static,
            ATTR_MAX_CURRENT: load_get.maxCurrent,
            ATTR_ATMEL_ERROR: bool(is_error.error),
            ATTR_NETWORK_STATUS_ETHERNET: network_status.ethernet == "Connected",
            ATTR_NETWORK_STATUS_WLAN: network_status.wlan == "Connected",
            ATTR_CHARGER_STATUS: transaction_status.ocppCpState,
            ATTR_CHARGING_IS_ON: transaction_status.ocppCpState != "Available",
            ATTR_CHARGER_CURRENT_RATE: transaction_status.currentChargeRate,
            ATTR_CHARGER_SECONDS_SINCE_START: transaction_status.secondsSinceChargeStart,
            ATTR_TRANSACTION_CURRENT_ENERGY: transaction_status.currentTransactionEnergy,
            ATTR_LAST_5_TRANSACTIONS: last_5,
        }
