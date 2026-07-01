"""Shared entity base class."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import _SrneBaseCoordinator


def _build_entity_name(register: dict) -> str:
    """Build the display name. Always static — never changes after entity creation."""
    param = register.get("param_number")
    name = register["name"]
    return f"({param:02d}) {name}" if param is not None else name


class SrneInverterEntity(CoordinatorEntity[_SrneBaseCoordinator]):
    """Base entity for all SRNE inverter entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: _SrneBaseCoordinator,
        register: dict,
        config_entry_id: str,
        device_model: str,
        device_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._register = register
        self._attr_unique_id = f"{config_entry_id}_{register['key']}"
        self._attr_name = _build_entity_name(register)
        self._attr_attribution = register.get("note")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry_id)},
            manufacturer=MANUFACTURER,
            model=device_model,
            name=device_name,
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data is not None
            and self._register["key"] in self.coordinator.data
        )
