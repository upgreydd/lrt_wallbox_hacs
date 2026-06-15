"""Configuration flow for LRT Wallbox integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from lrt_wallbox import WallboxAuthError, WallboxClient, WallboxError

from .const import (
    CONF_MAX_LOAD,
    CONF_OCPP_WSS_URL,
    CONF_REFRESH_INTERVAL,
    DOMAIN,
)
from .helpers import tag_id_to_hex

_LOGGER = logging.getLogger(__name__)


def _connection_schema(current: dict[str, Any]) -> vol.Schema:
    """Schema for connection/credential fields (stored in entry.data)."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=current.get(CONF_NAME, "LRT Wallbox")): vol.All(
                cv.string, vol.Length(min=3, max=20)
            ),
            vol.Required(CONF_HOST, default=current.get(CONF_HOST)): cv.string,
            vol.Required(CONF_USERNAME, default=current.get(CONF_USERNAME)): vol.All(
                cv.string, vol.Length(min=3, max=20)
            ),
            vol.Required(CONF_PASSWORD, default=current.get(CONF_PASSWORD)): vol.All(
                cv.string, vol.Length(min=3, max=20)
            ),
        }
    )


def _tunables_schema(current: dict[str, Any]) -> vol.Schema:
    """Schema for tunable settings (stored in entry.options)."""
    return vol.Schema(
        {
            vol.Required(CONF_MAX_LOAD, default=current.get(CONF_MAX_LOAD, 16)): vol.All(
                cv.positive_int, vol.Range(min=6, max=32)
            ),
            vol.Required(
                CONF_REFRESH_INTERVAL, default=current.get(CONF_REFRESH_INTERVAL, 5)
            ): vol.All(cv.positive_int, vol.Range(min=3, max=300)),
            vol.Optional(
                CONF_OCPP_WSS_URL, default=current.get(CONF_OCPP_WSS_URL, "")
            ): vol.All(cv.string, vol.Length(min=0, max=50)),
        }
    )


def _full_schema(current: dict[str, Any]) -> vol.Schema:
    """Combined schema for the initial setup step."""
    return _connection_schema(current).extend(_tunables_schema(current).schema)


async def _validate_credentials(hass, data: dict[str, Any]) -> None:
    """Verify host+credentials by performing a password-authenticated call.

    Raises WallboxError (or a subclass) on failure.
    """
    client = WallboxClient(
        ip=data[CONF_HOST],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        key_path=hass.config.path(DOMAIN, "config_flow_probe"),
    )
    await hass.async_add_executor_job(client.user_current)


def _split(user_input: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a combined form into (connection_data, tunable_options)."""
    connection = {
        k: user_input[k]
        for k in (CONF_NAME, CONF_HOST, CONF_USERNAME, CONF_PASSWORD)
    }
    options = {
        k: user_input[k]
        for k in (CONF_MAX_LOAD, CONF_REFRESH_INTERVAL, CONF_OCPP_WSS_URL)
        if k in user_input
    }
    return connection, options


class LrtWallboxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LRT Wallbox."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step of the config flow."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _validate_credentials(self.hass, user_input)
            except WallboxAuthError:
                errors["base"] = "invalid_auth"
            except WallboxError:
                errors["base"] = "cannot_connect"
            else:
                connection, options = _split(user_input)
                return self.async_create_entry(
                    title=f"LRT Wallbox @ {user_input[CONF_HOST]} ({user_input[CONF_USERNAME]})",
                    data=connection,
                    options=options,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_full_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when credentials stop working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Prompt for a new password and validate it."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            candidate = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            try:
                await _validate_credentials(self.hass, candidate)
            except WallboxAuthError:
                errors["base"] = "invalid_auth"
            except WallboxError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data=candidate)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required(CONF_PASSWORD): vol.All(cv.string, vol.Length(min=3, max=20))}
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow changing the host/credentials of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _validate_credentials(self.hass, user_input)
            except WallboxAuthError:
                errors["base"] = "invalid_auth"
            except WallboxError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data=user_input)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(dict(entry.data)),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlow:
        """Return the options flow handler for this config entry."""
        return LrtWallboxOptionsFlow()


class LrtWallboxOptionsFlow(config_entries.OptionsFlow):
    """Options flow for LRT Wallbox integration.

    Note: do NOT assign ``self.config_entry`` here — it is provided automatically
    as a read-only property by the base class (assigning it raises on HA >= 2025.12).
    """

    def __init__(self) -> None:
        """Initialize transient options-flow state."""
        self.tag_id: list[int] | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Present the initial options step."""
        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema(
                    {
                        vol.Required("choice"): SelectSelector(
                            SelectSelectorConfig(
                                options=["general", "rfid", "rfid_delete"],
                                translation_key="choice",
                                multiple=False,
                                mode=SelectSelectorMode.LIST,
                            )
                        )
                    }
                ),
            )

        choice = user_input["choice"]
        if choice == "general":
            return await self.async_step_general()
        if choice == "rfid":
            return await self.async_step_start_scan()
        if choice == "rfid_delete":
            return await self.async_step_rfid_delete()
        return self.async_abort(reason="invalid_choice")

    async def async_step_general(self, user_input: dict[str, Any] | None = None):
        """Edit the tunable settings (stored in entry.options)."""
        if user_input is not None:
            # Returning here writes entry.options; the update listener reloads.
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="general",
            data_schema=_tunables_schema(current),
        )

    def _executor(self):
        """Get the live transport for the current entry."""
        return self.config_entry.runtime_data.coordinator.executor

    async def async_step_start_scan(self, user_input: dict[str, Any] | None = None):
        """Start scanning for a new RFID tag."""
        try:
            self.tag_id = await self._executor().call("rfid_scan")
        except WallboxError as e:
            return self.async_abort(
                reason="rfid_scan_failed",
                description_placeholders={"error": e.message},
            )
        return await self.async_step_enter_name()

    async def async_step_enter_name(self, user_input: dict[str, Any] | None = None):
        """Prompt for a name for the new RFID tag."""
        if user_input is not None:
            try:
                await self._executor().call("rfid_add", self.tag_id, user_input["name"])
            except WallboxError as e:
                return self.async_abort(
                    reason="rfid_add_failed",
                    description_placeholders={"error": e.message},
                )
            return self.async_create_entry(title="", data=dict(self.config_entry.options))

        return self.async_show_form(
            step_id="enter_name",
            data_schema=vol.Schema({vol.Required("name"): str}),
        )

    async def async_step_rfid_delete(self, user_input: dict[str, Any] | None = None):
        """Handle deletion of an RFID tag."""
        try:
            rfid_tags = await self._executor().call("rfid_get")
        except WallboxError as e:
            return self.async_abort(
                reason="rfid_delete_failed",
                description_placeholders={"error": e.message},
            )
        if not rfid_tags:
            return self.async_abort(reason="rfid_empty")

        tag_choices = {
            tag_id_to_hex(tag.tagId): f"{tag_id_to_hex(tag.tagId)} - {tag.name}"
            for tag in rfid_tags
        }

        if user_input is not None:
            selected_tag_id_hex = user_input["tag_id"]
            selected_tag = next(
                (tag for tag in rfid_tags if tag_id_to_hex(tag.tagId) == selected_tag_id_hex),
                None,
            )
            if selected_tag is None:
                return self.async_abort(reason="rfid_not_found")
            try:
                await self._executor().call("rfid_delete", selected_tag.tagId)
            except WallboxError as e:
                return self.async_abort(
                    reason="rfid_delete_failed",
                    description_placeholders={"error": e.message},
                )
            return self.async_create_entry(title="", data=dict(self.config_entry.options))

        return self.async_show_form(
            step_id="rfid_delete",
            data_schema=vol.Schema({vol.Required("tag_id"): vol.In(tag_choices)}),
            last_step=True,
        )
