"""Number platform for the SRNE Inverter integration.

Covers writable registers with a continuous/numeric range (charge voltages,
current limits, capacity, etc.). Min/max/step come straight from the active
profile, so the HA UI slider itself enforces the same bounds the coordinator
checks again before writing — belt and suspenders, per the requirement that
out-of-range writes should be rejected rather than silently clamped or passed
through.
"""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_MODEL_NAME, DOMAIN
from .coordinator import SrneInverterCoordinator, SrneWriteValidationError
from .entity import SrneInverterEntity
from .modbus_client import SrneModbusError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities for all writable numeric registers."""
    coordinator: SrneInverterCoordinator = hass.data[DOMAIN][entry.entry_id]
    profile = coordinator.profile
    device_name = entry.title or DEFAULT_MODEL_NAME

    entities = [
        SrneNumber(coordinator, reg, entry.entry_id, DEFAULT_MODEL_NAME, device_name)
        for reg in profile.REGISTERS
        if reg["entity"] == "number"
    ]
    async_add_entities(entities)


class SrneNumber(SrneInverterEntity, NumberEntity):
    """A writable numeric config entity backed by one profile register."""

    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, register, config_entry_id, device_model, device_name):
        super().__init__(coordinator, register, config_entry_id, device_model, device_name)
        self._attr_native_unit_of_measurement = register.get("unit")
        self._attr_device_class = register.get("device_class")
        self._attr_native_min_value = register.get("min_value", 0)
        self._attr_native_max_value = register.get("max_value", 65535)
        self._attr_native_step = register.get("step", 1)

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._register["key"])

    async def async_set_native_value(self, value: float) -> None:
        """Validate (via the coordinator) and write the new value."""
        try:
            await self.coordinator.async_write_value(self._register["key"], value)
        except SrneWriteValidationError as err:
            raise HomeAssistantError(str(err)) from err
        except SrneModbusError as err:
            raise HomeAssistantError(
                f"Failed to write {self._register['name']}: {err}"
            ) from err
