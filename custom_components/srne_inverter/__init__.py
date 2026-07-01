"""The SRNE Inverter integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    CONF_PROFILE_ID, CONF_SLAVE_ID,
    DEFAULT_TIMEOUT, DOMAIN,
)
from .coordinator import SrneTelemetryCoordinator, SrneConfigCoordinator
from .modbus_client import SrneModbusClient
from .profiles import get_profile

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    profile = get_profile(entry.data[CONF_PROFILE_ID])
    client = SrneModbusClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        slave_id=entry.data[CONF_SLAVE_ID],
        timeout=DEFAULT_TIMEOUT,
    )

    telemetry_coordinator = SrneTelemetryCoordinator(hass, client, profile)
    config_coordinator = SrneConfigCoordinator(hass, client, profile)

    # Telemetry MUST succeed for the integration to load — it's the core data.
    # This raises ConfigEntryNotReady on failure, which is correct behaviour.
    await telemetry_coordinator.async_config_entry_first_refresh()

    # Config coordinator (E0xx/E2xx) is best-effort on startup.
    # If it fails (permission error, timeout, etc.) we still load the integration
    # so telemetry keeps running. Config entities will show Unknown until the
    # next scheduled refresh (1 hour) or until the integration is reloaded.
    try:
        await config_coordinator.async_refresh()
    except Exception as err:
        _LOGGER.warning(
            "Config register first refresh failed — telemetry will still run. "
            "Config entities will show Unknown until next hourly refresh. "
            "Error: %s", err
        )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "telemetry": telemetry_coordinator,
        "config": config_coordinator,
        "client": client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].async_close()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
