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

    # Update device registry with firmware/hardware versions from product info
    # registers, if they were read successfully in the first telemetry refresh.
    _async_update_device_info(hass, entry, telemetry_coordinator.data or {})
    return True


def _async_update_device_info(hass, entry, data: dict) -> None:
    """Write firmware/hw version into the HA device registry if available."""
    from homeassistant.helpers import device_registry as dr

    cpu1 = data.get("cpu1_sw_version")
    hw = data.get("hw_version_control")

    sw_version = f"V{int(cpu1)//100}.{int(cpu1)%100:02d}" if cpu1 else None
    hw_version = f"V{int(hw)//100}.{int(hw)%100:02d}" if hw else None

    if not sw_version and not hw_version:
        return

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    if device:
        dev_reg.async_update_device(
            device.id,
            sw_version=sw_version,
            hw_version=hw_version,
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].async_close()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
