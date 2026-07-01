"""Number platform for the SRNE Inverter integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_MODEL_NAME, DOMAIN
from .coordinator import SrneWriteValidationError
from .entity import SrneInverterEntity
from .modbus_client import SrneModbusError

_LOGGER = logging.getLogger(__name__)

_ICON_DEFAULT = None          # use platform default
_ICON_MODIFIED = "mdi:pencil-circle"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    config_coord = data["config"]
    profile = config_coord.profile
    device_name = entry.title or DEFAULT_MODEL_NAME

    entities = [
        SrneNumber(config_coord, reg, entry.entry_id, DEFAULT_MODEL_NAME, device_name)
        for reg in profile.REGISTERS
        if reg["entity"] == "number" and reg.get("param_number") is not None
    ]
    async_add_entities(entities)


class SrneNumber(SrneInverterEntity, NumberEntity):
    """A writable numeric config entity."""

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
    def icon(self) -> str | None:
        """Show pencil icon when value differs from factory default."""
        if self._default is None or not self.available:
            return _ICON_DEFAULT
        current = self.coordinator.data.get(self._register["key"])
        if current is None:
            return _ICON_DEFAULT
        if round(current, 6) != round(float(self._default), 6):
            return _ICON_MODIFIED
        return _ICON_DEFAULT

    @property
    def native_value(self):
        if not self.available:
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
            raise HomeAssistantError(f"Write failed: {err}") from err
