"""Shared entity base class.

Every entity (sensor, number, select) descends from SrneInverterEntity so
they all attach to the same DeviceInfo — this is what makes them show up
grouped under one Device page in Settings > Devices & Services, rather than
as a scattered flat entity list.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SrneInverterCoordinator


class SrneInverterEntity(CoordinatorEntity[SrneInverterCoordinator]):
    """Base entity for all SRNE inverter entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SrneInverterCoordinator,
        register: dict,
        config_entry_id: str,
        device_model: str,
        device_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._register = register
        self._attr_unique_id = f"{config_entry_id}_{register['key']}"
        self._attr_name = register["name"]
        self._attr_attribution = register.get("note")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry_id)},
            manufacturer=MANUFACTURER,
            model=device_model,
            name=device_name,
        )

    @property
    def available(self) -> bool:
        """An entity is available if the coordinator has a value for its key."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._register["key"] in self.coordinator.data
        )
