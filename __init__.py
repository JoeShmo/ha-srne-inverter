"""The SRNE Inverter integration.

Provides a Home Assistant Device for an SRNE-protocol energy storage
inverter/charger (or rebrand thereof, e.g. Sungold) connected via Modbus
RTU-over-TCP — typically through a ser2net bridge on a Pi holding the
USB-serial connection to the unit.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_PROFILE_ID,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .coordinator import SrneInverterCoordinator
from .modbus_client import SrneModbusClient
from .profiles import get_profile

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one SRNE inverter from a config entry."""
    profile = get_profile(entry.data[CONF_PROFILE_ID])

    client = SrneModbusClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        slave_id=entry.data[CONF_SLAVE_ID],
        timeout=DEFAULT_TIMEOUT,
    )

    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    coordinator = SrneInverterCoordinator(
        hass, client=client, profile=profile, scan_interval=scan_interval
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: SrneInverterCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.async_close()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change (e.g. scan interval)."""
    await hass.config_entries.async_reload(entry.entry_id)
