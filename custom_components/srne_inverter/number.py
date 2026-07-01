"""Number platform for the SRNE Inverter integration."""

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
        self._default = register.get("default")

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._register["key"])

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {}
        if self._default is not None:
            attrs["default_value"] = self._default
            current = self.native_value
            if current is not None and self.available:
                attrs["changed_from_default"] = (
                    round(current, 6) != round(float(self._default), 6)
                )
        return attrs

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.async_write_value(self._register["key"], value)
        except SrneWriteValidationError as err:
            raise HomeAssistantError(str(err)) from err
        except SrneModbusError as err:
            raise HomeAssistantError(
                f"Failed to write {self._register['name']}: {err}"
            ) from err
