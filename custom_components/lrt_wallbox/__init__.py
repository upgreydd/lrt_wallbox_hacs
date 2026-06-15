"""Integration for LRT Wallbox chargers."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from lrt_wallbox import WallboxAuthError, WallboxClient, WallboxPermissionError

from .const import CONF_OCPP_WSS_URL, CONF_REFRESH_INTERVAL, DOMAIN, PLATFORMS
from .coordinator import LrtWallboxCoordinator
from .helpers import WallboxClientExecutor
from .models import LrtConfigEntry, LrtRuntimeData

_LOGGER = logging.getLogger(__name__)


def get_conf(entry: LrtConfigEntry, key: str, default=None):
    """Read a tunable, preferring `options` and falling back to `data`.

    Existing entries created before options were used still carry their values
    in `data`; new/updated entries store tunables in `options`.
    """
    return entry.options.get(key, entry.data.get(key, default))


async def async_setup_entry(hass: HomeAssistant, entry: LrtConfigEntry) -> bool:
    """Set up LRT Wallbox from a config entry."""
    client = WallboxClient(
        ip=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        # Keep the device keypair in HA's config dir (per-entry), never in the
        # installed site-packages directory.
        key_path=hass.config.path(DOMAIN, entry.entry_id),
    )
    executor = WallboxClientExecutor(client, hass)

    coordinator = LrtWallboxCoordinator(
        hass,
        entry,
        executor,
        update_interval=int(get_conf(entry, CONF_REFRESH_INTERVAL, 5)),
    )

    try:
        await coordinator.async_init_static()
        await _maybe_set_ocpp_url(coordinator, get_conf(entry, CONF_OCPP_WSS_URL, ""))
        await coordinator.async_config_entry_first_refresh()
    except (ConfigEntryAuthFailed, ConfigEntryNotReady):
        await executor.shutdown()
        raise
    except (WallboxAuthError, WallboxPermissionError) as err:
        # Bad/expired credentials during the pre-refresh probe → start reauth.
        await executor.shutdown()
        raise ConfigEntryAuthFailed(str(err)) from err
    except Exception as err:
        await executor.shutdown()
        raise ConfigEntryNotReady(f"Wallbox not ready: {err}") from err

    entry.runtime_data = LrtRuntimeData(coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _maybe_set_ocpp_url(coordinator: LrtWallboxCoordinator, url: str) -> None:
    """Push the OCPP URL only when set and actually changed (idempotent)."""
    if not url:
        return
    current = await coordinator.executor.call("config_ocpp_get")
    if getattr(current, "url", None) != url:
        _LOGGER.debug("Updating OCPP URL on device")
        await coordinator.executor.call("config_ocpp_set", url)


async def _async_reload_entry(hass: HomeAssistant, entry: LrtConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: LrtConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and entry.runtime_data is not None:
        await entry.runtime_data.coordinator.executor.shutdown()
    return unloaded
