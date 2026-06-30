"""Select platform for the SRNE Inverter integration.

Covers writable registers whose value is a small fixed set of named options
(battery type, charge priority, output priority, enable/disable toggles that
are represented as registers rather than coils, etc.).
"""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
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
    """Set up select entities for all writable enum registers."""
    coordinator: SrneInverterCoordinator = hass.data[DOMAIN][entry.entry_id]
    profile = coordinator.profile
    device_name = entry.title or DEFAULT_MODEL_NAME

    entities = [
        SrneSelect(coordinator, reg, entry.entry_id, DEFAULT_MODEL_NAME, device_name)
        for reg in profile.REGISTERS
        if reg["entity"] == "select"
    ]
    async_add_entities(entities)


class SrneSelect(SrneInverterEntity, SelectEntity):
    """A writable enum config entity backed by one profile register."""

    def __init__(self, coordinator, register, config_entry_id, device_model, device_name):
        super().__init__(coordinator, register, config_entry_id, device_model, device_name)
        self._options_map: dict[int, str] = register["options"]
        self._reverse_map: dict[str, int] = {v: k for k, v in self._options_map.items()}
        self._attr_options = list(self._options_map.values())

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(self._register["key"])
        if raw is None:
            return None
        return self._options_map.get(int(raw))

    async def async_select_option(self, option: str) -> None:
        """Validate (via the coordinator) and write the new option."""
        raw_value = self._reverse_map.get(option)
        if raw_value is None:
            raise HomeAssistantError(f"Unknown option: {option}")
        try:
            await self.coordinator.async_write_value(self._register["key"], raw_value)
        except SrneWriteValidationError as err:
            raise HomeAssistantError(str(err)) from err
        except SrneModbusError as err:
            raise HomeAssistantError(
                f"Failed to write {self._register['name']}: {err}"
            ) from err
