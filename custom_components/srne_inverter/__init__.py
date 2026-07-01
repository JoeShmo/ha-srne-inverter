"""The SRNE Inverter integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_PROFILE_ID, CONF_SCAN_INTERVAL, CONF_SLAVE_ID,
    DEFAULT_SCAN_INTERVAL, DEFAULT_TIMEOUT, DOMAIN,
)
from .coordinator import (
    SrneTelemetryCoordinator, SrneConfigCoordinator,
    TELEMETRY_SCAN_INTERVAL, CONFIG_SCAN_INTERVAL,
)
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

    await telemetry_coordinator.async_config_entry_first_refresh()
    await config_coordinator.async_config_entry_first_refresh()

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
