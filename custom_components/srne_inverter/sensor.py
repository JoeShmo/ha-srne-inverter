"""Sensor platform — read-only telemetry entities."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_MODEL_NAME, DOMAIN
from .coordinator import _SrneBaseCoordinator
from .entity import SrneInverterEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    telemetry_coord = data["telemetry"]
    profile = telemetry_coord.profile
    device_name = entry.title or DEFAULT_MODEL_NAME

    entities: list[SensorEntity] = []
    for reg in profile.REGISTERS:
        if reg["entity"] != "sensor":
            continue
        entities.append(
            SrneSensor(telemetry_coord, reg, entry.entry_id, DEFAULT_MODEL_NAME, device_name)
        )

    if profile.get_register("device_temp_raw") is not None:
        for high_byte, key, name in [
            (True, "controller_temp", "Controller Temperature"),
            (False, "battery_temp", "Battery Temperature"),
        ]:
            entities.append(SrnePackedByteSensor(
                telemetry_coord, "device_temp_raw", key, name, high_byte,
                "°C", "temperature", entry.entry_id, DEFAULT_MODEL_NAME, device_name,
            ))

    async_add_entities(entities)
    async_add_entities([SrneQuarantineSensor(
        telemetry_coord, entry.entry_id, DEFAULT_MODEL_NAME, device_name
    )])


class SrneSensor(SrneInverterEntity, SensorEntity):
    def __init__(self, coordinator, register, config_entry_id, device_model, device_name):
        super().__init__(coordinator, register, config_entry_id, device_model, device_name)
        self._attr_native_unit_of_measurement = register.get("unit")
        self._attr_device_class = register.get("device_class")
        if register.get("device_class") != "enum":
            self._attr_state_class = "measurement"
        self._attr_entity_registry_enabled_default = register.get("enabled_by_default", True)
        self._options = register.get("options")

    @property
    def native_value(self):
        if not self.available:
            return None
        value = self.coordinator.data.get(self._register["key"])
        if value is None:
            return None
        if self._options is not None:
            return self._options.get(int(value), f"Unknown ({int(value)})")
        return value


class SrnePackedByteSensor(SrneInverterEntity, SensorEntity):
    def __init__(self, coordinator, source_key, key, name, high_byte,
                 unit, device_class, config_entry_id, device_model, device_name):
        pseudo = {"key": key, "name": name, "note": None, "param_number": None}
        super().__init__(coordinator, pseudo, config_entry_id, device_model, device_name)
        self._source_key = source_key
        self._high_byte = high_byte
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = "measurement"

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self._source_key in self.coordinator.data
        )

    @property
    def native_value(self):
        if not self.available:
            return None
        raw = int(self.coordinator.data.get(self._source_key, 0))
        byte_value = (raw >> 8) & 0xFF if self._high_byte else raw & 0xFF
        sign = -1 if byte_value & 0x80 else 1
        return sign * (byte_value & 0x7F)


class SrneQuarantineSensor(SrneInverterEntity, SensorEntity):
    _attr_entity_category = "diagnostic"

    def __init__(self, coordinator, config_entry_id, device_model, device_name):
        pseudo = {"key": "quarantined_registers", "name": "Quarantined Registers",
                  "note": "Registers excluded after repeated read failures.", "param_number": None}
        super().__init__(coordinator, pseudo, config_entry_id, device_model, device_name)

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> int:
        return len(self.coordinator.quarantined_keys)

    @property
    def extra_state_attributes(self) -> dict:
        return {"quarantined_keys": sorted(self.coordinator.quarantined_keys)}
