"""The SRNE Inverter integration."""

from __future__ import annotations

import logging
import struct

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_PROFILE_ID, CONF_SLAVE_ID,
    DEFAULT_TIMEOUT, DOMAIN,
)
from .coordinator import SrneTelemetryCoordinator, SrneConfigCoordinator
from .modbus_client import SrneModbusClient, SrneModbusError
from .profiles import get_profile

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT]

_SN_ADDRESS = 0x0035
_SN_LENGTH = 20  # 20 registers = 40 ASCII chars


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    profile_id = entry.options.get(CONF_PROFILE_ID, entry.data.get(CONF_PROFILE_ID))
    profile = get_profile(profile_id)
    client = SrneModbusClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        slave_id=entry.data[CONF_SLAVE_ID],
        timeout=DEFAULT_TIMEOUT,
    )

    telemetry_coordinator = SrneTelemetryCoordinator(hass, client, profile)
    config_coordinator = SrneConfigCoordinator(hass, client, profile)

    await telemetry_coordinator.async_config_entry_first_refresh()

    try:
        await config_coordinator.async_refresh()
    except Exception as err:
        _LOGGER.warning(
            "Config register first refresh failed — telemetry will still run. "
            "Config entities will show Unknown until next hourly refresh. "
            "Error: %s", err
        )

    # Read serial number (ASCII string at 0x0035, 20 registers).
    # Done separately since it's a multi-register ASCII read, not a standard
    # uint16 register — the coordinator doesn't handle string registers.
    serial_number = await _async_read_serial_number(client)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "telemetry": telemetry_coordinator,
        "config": config_coordinator,
        "client": client,
        "serial_number": serial_number,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_update_device_info(hass, entry, telemetry_coordinator.data or {}, serial_number)
    return True


async def _async_read_serial_number(client: SrneModbusClient) -> str | None:
    """Read the ASCII serial number from 0x0035 (20 registers = 40 chars)."""
    try:
        await client.async_connect()
        regs = await client.async_read_registers(_SN_ADDRESS, _SN_LENGTH)
        raw = b"".join(struct.pack(">H", r) for r in regs)
        sn = raw.rstrip(b"\x00").decode("ascii", errors="replace").strip()
        return sn if sn else None
    except (SrneModbusError, Exception) as err:
        _LOGGER.debug("Could not read serial number: %s", err)
        return None
    finally:
        await client.async_close()


def _async_update_device_info(hass, entry, data: dict, serial_number: str | None) -> None:
    """Write firmware/hw version and serial number into the HA device registry."""
    from homeassistant.helpers import device_registry as dr

    cpu1 = data.get("cpu1_sw_version")
    hw = data.get("hw_version_control")

    sw_version = f"V{int(cpu1)//100}.{int(cpu1)%100:02d}" if cpu1 else None
    hw_version = f"V{int(hw)//100}.{int(hw)%100:02d}" if hw else None

    if not sw_version and not hw_version and not serial_number:
        return

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    if device:
        update_kwargs = {}
        if sw_version:
            update_kwargs["sw_version"] = sw_version
        if hw_version:
            update_kwargs["hw_version"] = hw_version
        if serial_number:
            # HA device registry uses serial_number field for this
            update_kwargs["serial_number"] = serial_number
        if update_kwargs:
            dev_reg.async_update_device(device.id, **update_kwargs)
            _LOGGER.debug(
                "Updated device info: sw=%s hw=%s sn=%s",
                sw_version, hw_version, serial_number,
            )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].async_close()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
