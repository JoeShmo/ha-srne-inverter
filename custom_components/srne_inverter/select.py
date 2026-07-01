"""Select platform for the SRNE Inverter integration."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_MODEL_NAME, DOMAIN
from .coordinator import SrneWriteValidationError
from .entity import SrneInverterEntity
from .modbus_client import SrneModbusError

_LOGGER = logging.getLogger(__name__)

_ICON_DEFAULT = None
_ICON_MODIFIED = "mdi:pencil-circle"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    config_coord = data["config"]
    profile = config_coord.profile
    device_name = entry.title or DEFAULT_MODEL_NAME

    entities = [
        SrneSelect(config_coord, reg, entry.entry_id, DEFAULT_MODEL_NAME, device_name)
        for reg in profile.REGISTERS
        if reg["entity"] == "select" and reg.get("param_number") is not None
    ]
    async_add_entities(entities)


class SrneSelect(SrneInverterEntity, SelectEntity):
    """A writable enum config entity."""

    def __init__(self, coordinator, register, config_entry_id, device_model, device_name):
        super().__init__(coordinator, register, config_entry_id, device_model, device_name)
        self._options_map: dict[int, str] = register["options"]
        self._reverse_map: dict[str, int] = {v: k for k, v in self._options_map.items()}
        self._attr_options = list(self._options_map.values())
        self._default_raw = register.get("default")

    @property
    def icon(self) -> str | None:
        """Show pencil icon when value differs from factory default."""
        if self._default_raw is None or not self.available:
            return _ICON_DEFAULT
        current = self.coordinator.data.get(self._register["key"])
        if current is None:
            return _ICON_DEFAULT
        if int(current) != int(self._default_raw):
            return _ICON_MODIFIED
        return _ICON_DEFAULT

    @property
    def current_option(self) -> str | None:
        if not self.available:
            return None
        raw = self.coordinator.data.get(self._register["key"])
        if raw is None:
            return None
        return self._options_map.get(int(raw))

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {}
        if self._default_raw is not None:
            default_label = self._options_map.get(int(self._default_raw))
            attrs["default_value"] = default_label
            current = self.current_option
            if current is not None and self.available:
                attrs["changed_from_default"] = (current != default_label)
        return attrs

    async def async_select_option(self, option: str) -> None:
        raw_value = self._reverse_map.get(option)
        if raw_value is None:
            raise HomeAssistantError(f"Unknown option: {option}")
        try:
            await self.coordinator.async_write_value(self._register["key"], raw_value)
        except SrneWriteValidationError as err:
            raise HomeAssistantError(str(err)) from err
        except SrneModbusError as err:
            raise HomeAssistantError(f"Write failed: {err}") from err
