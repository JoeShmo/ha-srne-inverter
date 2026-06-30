"""Config flow for the SRNE Inverter integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_PROFILE_ID,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .modbus_client import SrneModbusClient, SrneModbusError
from .profiles import DEFAULT_PROFILE_ID, profile_choices

_LOGGER = logging.getLogger(__name__)


async def _async_validate_connection(
    host: str, port: int, slave_id: int
) -> str | None:
    """Try a single register read to confirm the device is reachable.

    Returns an error string for the form, or None on success. Reads the
    well-known Battery SOC register (0x0100), which is present in every
    SRNE energy-storage-inverter profile and is harmless to read.
    """
    client = SrneModbusClient(host=host, port=port, slave_id=slave_id, timeout=DEFAULT_TIMEOUT)
    try:
        await client.async_read_registers(0x0100, 1)
    except SrneModbusError as err:
        _LOGGER.debug("Connection validation failed: %s", err)
        return "cannot_connect"
    finally:
        await client.async_close()
    return None


class SrneInverterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for adding an SRNE inverter."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """First (and only) step: collect connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            error = await _async_validate_connection(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_SLAVE_ID],
            )
            if error:
                errors["base"] = error
            else:
                # Prevent adding the same host:port:slave combination twice.
                unique_id = (
                    f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}:"
                    f"{user_input[CONF_SLAVE_ID]}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

        choices = profile_choices()
        data_schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="SRNE Inverter"): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_SLAVE_ID, default=1): vol.All(
                    int, vol.Range(min=1, max=247)
                ),
                vol.Required(
                    CONF_PROFILE_ID, default=DEFAULT_PROFILE_ID
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=pid, label=name)
                            for pid, name in choices.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SrneInverterOptionsFlow(config_entry)


class SrneInverterOptionsFlow(OptionsFlow):
    """Options flow: lets the user tune polling interval after setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        data_schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    int, vol.Range(min=5, max=300)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=data_schema)
