"""Sensor platform for the SRNE Inverter integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEFAULT_MODEL_NAME, DOMAIN
from .coordinator import SrneInverterCoordinator
from .entity import SrneInverterEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from the active profile's register list."""
    coordinator: SrneInverterCoordinator = hass.data[DOMAIN][entry.entry_id]
    profile = coordinator.profile
    device_name = entry.title or DEFAULT_MODEL_NAME

    entities: list[SensorEntity] = []
    for reg in profile.REGISTERS:
        if reg["entity"] != "sensor":
            continue
        entities.append(
            SrneSensor(coordinator, reg, entry.entry_id, DEFAULT_MODEL_NAME, device_name)
        )

    # Derived sensors that split a packed register into human values.
    # Currently just the controller/battery temperature byte-pair; add more
    # here if a profile defines other packed registers worth splitting.
    if profile.get_register("device_temp_raw") is not None:
        entities.append(
            SrnePackedByteSensor(
                coordinator,
                source_key="device_temp_raw",
                key="controller_temp",
                name="Controller Temperature",
                high_byte=True,
                unit="°C",
                device_class="temperature",
                config_entry_id=entry.entry_id,
                device_model=DEFAULT_MODEL_NAME,
                device_name=device_name,
            )
        )
        entities.append(
            SrnePackedByteSensor(
                coordinator,
                source_key="device_temp_raw",
                key="battery_temp",
                name="Battery Temperature",
                high_byte=False,
                unit="°C",
                device_class="temperature",
                config_entry_id=entry.entry_id,
                device_model=DEFAULT_MODEL_NAME,
                device_name=device_name,
            )
        )

    async_add_entities(entities)

    # Diagnostic sensor surfacing which registers (if any) have been
    # quarantined after repeated read failures — visible in the UI rather
    # than only in the logs, addressing the exact gap the user ran into
    # with solax_modbus's quarantine feature ("there were two quarantined
    # values but I don't know what they were").
    async_add_entities([SrneQuarantineSensor(coordinator, entry.entry_id, DEFAULT_MODEL_NAME, device_name)])


class SrneSensor(SrneInverterEntity, SensorEntity):
    """A sensor entity backed directly by one profile register."""

    def __init__(self, coordinator, register, config_entry_id, device_model, device_name):
        super().__init__(coordinator, register, config_entry_id, device_model, device_name)
        self._attr_native_unit_of_measurement = register.get("unit")
        self._attr_device_class = register.get("device_class")
        if register.get("device_class") != "enum":
            self._attr_state_class = "measurement"
        self._attr_entity_registry_enabled_default = register.get(
            "enabled_by_default", True
        )
        self._options = register.get("options")

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self._register["key"])
        if value is None:
            return None
        if self._options is not None:
            return self._options.get(int(value), f"Unknown ({int(value)})")
        return value


class SrneQuarantineSensor(SrneInverterEntity, SensorEntity):
    """Diagnostic sensor showing the count and identity of quarantined registers.

    A register is quarantined after repeatedly failing to read (see
    coordinator._MAX_CONSECUTIVE_FAILURES). The state is the count, and the
    full list of quarantined register keys is available as an attribute —
    surfaced in the UI specifically so this information isn't only
    discoverable by digging through debug logs.
    """

    _attr_entity_category = "diagnostic"

    def __init__(self, coordinator, config_entry_id, device_model, device_name):
        pseudo_register = {
            "key": "quarantined_registers",
            "name": "Quarantined Registers",
            "note": "Registers excluded after repeated read failures. See "
            "attributes for the full list of affected register keys.",
        }
        super().__init__(coordinator, pseudo_register, config_entry_id, device_model, device_name)
        self._attr_state_class = None

    @property
    def available(self) -> bool:
        # Always available — this reflects coordinator internal state, not
        # a register read, so it shouldn't go unavailable just because some
        # other register failed.
        return True

    @property
    def native_value(self) -> int:
        return len(self.coordinator.quarantined_keys)

    @property
    def extra_state_attributes(self) -> dict:
        return {"quarantined_keys": sorted(self.coordinator.quarantined_keys)}


class SrnePackedByteSensor(SrneInverterEntity, SensorEntity):
    """Derived sensor that reads one byte out of a packed 16-bit register.

    The SRNE protocol packs two independent 8-bit values (e.g. controller
    temp + battery temp) into a single register. This entity reads the
    underlying raw register from the coordinator's cache and extracts
    either the high or low byte, interpreted as a signed 8-bit value
    per the protocol's "b7 sign bit" convention for temperature bytes.
    """

    def __init__(
        self,
        coordinator,
        source_key: str,
        key: str,
        name: str,
        high_byte: bool,
        unit: str,
        device_class: str,
        config_entry_id: str,
        device_model: str,
        device_name: str,
    ) -> None:
        # Build a lightweight pseudo-register dict so the shared base class
        # constructor (which expects register-shaped data) works unchanged.
        pseudo_register = {"key": key, "name": name, "note": None}
        super().__init__(
            coordinator, pseudo_register, config_entry_id, device_model, device_name
        )
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
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(self._source_key)
        if raw is None:
            return None
        raw = int(raw)
        byte_value = (raw >> 8) & 0xFF if self._high_byte else raw & 0xFF
        # Per protocol: bit 7 is a sign bit, bits 0-6 are magnitude.
        sign = -1 if byte_value & 0x80 else 1
        magnitude = byte_value & 0x7F
        return sign * magnitude
