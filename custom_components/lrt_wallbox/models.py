"""Runtime data types for the LRT Wallbox integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .coordinator import LrtWallboxCoordinator


@dataclass
class LrtRuntimeData:
    """Objects kept alive for the lifetime of a config entry (Bronze `runtime-data`)."""

    coordinator: LrtWallboxCoordinator


type LrtConfigEntry = ConfigEntry[LrtRuntimeData]
