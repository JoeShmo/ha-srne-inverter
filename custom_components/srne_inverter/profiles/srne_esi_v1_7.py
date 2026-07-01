"""Register profile: SRNE Energy Storage Inverter Modbus protocol V1.7 / V1.92.

Covers SRNE HYP-series hybrid inverter/chargers and rebrands thereof
(e.g. Sungold SPH series). Parameter numbers (param_number) and defaults
are taken directly from the official HYP4850U100-H User Manual V2.6
(2025-04-11), Section 3.2 Setup Parameters Description. Modbus register
addresses are from the SRNE Energy Storage Inverter MODBUS Communication
Protocol V1.7 / V1.92 (cross-referenced against independent Modbus traffic
captures for confirmation where possible).

To add a second SRNE protocol family (e.g. standalone ML/MT charge
controller), create a new sibling file in this profiles/ package and
register it in profiles/__init__.py. Nothing else changes.

Field reference:
  key          - stable internal id
  name         - display name shown in HA (param_number prepended by entity layer)
  address      - Modbus holding register address (int)
  length       - number of 16-bit registers (1 unless noted)
  data_type    - "uint16" | "int16" | "uint32" | "int32"
  access       - "r" read-only | "rw" read-write
  entity       - "sensor" | "number" | "select" | "binary_sensor"
  scale        - multiply raw value by this to get real-world value
  unit         - HA unit_of_measurement string, or None
  device_class - HA device_class string, or None
  param_number - front-panel LCD parameter number from manual (int or None)
  default      - factory default in real-world (scaled) units, or None if unknown
  min_value    - for number entities: minimum real-world value (enforced on write)
  max_value    - for number entities: maximum real-world value (enforced on write)
  step         - for number entities: UI step size in real-world units
  options      - for select entities: {raw_int: label}
  category     - UI grouping: "telemetry" | "battery_config" | "inverter_config"
  enabled_by_default - False hides in HA until user explicitly enables
  note         - shown as entity description/attribution in HA UI
"""

from __future__ import annotations

PROFILE_ID = "srne_esi_v1_7"
PROFILE_NAME = "SRNE Energy Storage Inverter (HYP series / rebrands, V1.7+)"

DEFAULT_SLAVE_ID = 1

# ---------------------------------------------------------------------------
# Enum option tables
# ---------------------------------------------------------------------------

SUPPLY_PRIORITY_OPTIONS = {
    0: "PV First (AC1ST)",
    1: "Battery First (BT1ST)",
    2: "Solar First (PV1ST)",
    3: "Mix Load (default)",
}

CHARGE_MODE_OPTIONS = {
    0: "Only PV",
    1: "Hybrid (PV + Grid)",
}

BATTERY_TYPE_OPTIONS = {
    0: "User Defined",
    1: "Sealed Lead-Acid (SLd)",
    2: "Flooded Lead-Acid (FLd)",
    3: "GEL (default)",
    4: "LFP 14S",
    5: "LFP 15S",
    6: "LFP 16S",
    7: "NCM 13S",
    8: "NCM 14S",
    9: "No Battery",
}

AC_INPUT_RANGE_OPTIONS = {
    0: "UPS (narrow range)",
    1: "APL (wide range)",
}

ENABLE_DISABLE_OPTIONS = {
    0: "Disable",
    1: "Enable",
}

COMM_FUNCTION_OPTIONS = {
    0: "SLA (PC/host monitor)",
    1: "485 (BMS communication)",
}

BMS_PROTOCOL_OPTIONS = {
    0: "PAC (PACE)",
    1: "RDA (Ritar)",
    2: "AOG (AllGrand)",
    3: "OLT (Oliter)",
    4: "HWD (Sunwoda)",
    5: "DAQ (Daking)",
    6: "WOW (SRNE)",
    7: "PYL (Pylontech)",
    8: "UOL (Weilan)",
}

CHARGE_CURRENT_LIMIT_OPTIONS = {
    0: "LC SET (use Parameter 07 limit)",
    1: "LC BMS (BMS limit, default)",
    2: "LC INV (inverter logic limit)",
}

CHARGE_STATE_OPTIONS = {
    0: "Off",
    1: "Quick charge",
    2: "Constant voltage",
    4: "Float",
    5: "Reserved",
    6: "Li battery activate",
    7: "Reserved",
}

MACHINE_STATE_OPTIONS = {
    0: "Power-up delay",
    1: "Waiting",
    2: "Initialization",
    3: "Soft start",
    4: "Mains powered",
    5: "Inverter powered",
    6: "Inverter to mains",
    7: "Mains to inverter",
    8: "Battery activate",
    9: "Shutdown by user",
    10: "Fault",
}

# ---------------------------------------------------------------------------
# Register table
# ---------------------------------------------------------------------------

REGISTERS: list[dict] = [

    # ===================================================================
    # TELEMETRY — read-only (0x01xx / 0x02xx blocks)
    # ===================================================================

    {
        "key": "battery_soc",
        "name": "Battery SOC",
        "address": 0x0100,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": "%", "device_class": "battery",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "battery_voltage",
        "name": "Battery Voltage",
        "address": 0x0101,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "battery_current",
        "name": "Battery Current",
        "address": 0x0102,
        "length": 1, "data_type": "int16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "A", "device_class": "current",
        "param_number": None, "default": None,
        "category": "telemetry",
        "note": "Signed: positive = charging, negative = discharging.",
    },
    {
        "key": "device_temp_raw",
        "name": "Device Temperature (packed raw)",
        "address": 0x0103,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": None, "device_class": None,
        "param_number": None, "default": None,
        "category": "telemetry",
        "enabled_by_default": False,
        "note": "High byte = controller temp °C, low byte = battery temp °C. "
                "Split into derived sensors by the sensor platform.",
    },
    {
        "key": "pv1_voltage",
        "name": "PV1 Voltage",
        "address": 0x0107,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "pv1_current",
        "name": "PV1 Current",
        "address": 0x0108,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "A", "device_class": "current",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "pv1_power",
        "name": "PV1 Power",
        "address": 0x0109,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": "W", "device_class": "power",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "charge_state",
        "name": "Charge State",
        "address": 0x010B,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": None, "device_class": "enum",
        "options": CHARGE_STATE_OPTIONS,
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "charge_power_total",
        "name": "Charge Power Total",
        "address": 0x010E,
        "length": 1, "data_type": "int16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": "W", "device_class": "power",
        "param_number": None, "default": None,
        "category": "telemetry",
        "note": "Signed (positive = charging, negative = discharging). "
                "Confirmed as signed int16 against solax_modbus SRNE plugin.",
    },
    {
        "key": "pv_charge_current",
        "name": "PV Charge Current",
        "address": 0x0224,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "A", "device_class": "current",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "machine_state",
        "name": "Machine State",
        "address": 0x0210,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": None, "device_class": "enum",
        "options": MACHINE_STATE_OPTIONS,
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "bus_voltage",
        "name": "Bus Voltage",
        "address": 0x0212,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "param_number": None, "default": None,
        "category": "telemetry",
        "enabled_by_default": False,
    },
    {
        "key": "grid_voltage",
        "name": "Grid Voltage",
        "address": 0x0213,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "grid_current",
        "name": "Grid Current",
        "address": 0x0214,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "A", "device_class": "current",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "grid_frequency",
        "name": "Grid Frequency",
        "address": 0x0215,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 0.01, "unit": "Hz", "device_class": "frequency",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "inverter_output_voltage",
        "name": "Inverter Output Voltage",
        "address": 0x0216,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "inverter_output_current",
        "name": "Inverter Output Current",
        "address": 0x0217,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "A", "device_class": "current",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "inverter_frequency",
        "name": "Inverter Frequency",
        "address": 0x0218,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 0.01, "unit": "Hz", "device_class": "frequency",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "load_current",
        "name": "Load Current",
        "address": 0x0219,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "A", "device_class": "current",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "load_active_power",
        "name": "Load Active Power",
        "address": 0x021B,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": "W", "device_class": "power",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "load_apparent_power",
        "name": "Load Apparent Power",
        "address": 0x021C,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": "VA", "device_class": "apparent_power",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "mains_charge_current",
        "name": "Mains Charge Current (measured)",
        "address": 0x021E,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "A", "device_class": "current",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "load_ratio",
        "name": "Load Ratio",
        "address": 0x021F,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": "%", "device_class": None,
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "heatsink_a_temp",
        "name": "Heatsink A Temperature",
        "address": 0x0220,
        "length": 1, "data_type": "int16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "°C", "device_class": "temperature",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "heatsink_b_temp",
        "name": "Heatsink B Temperature",
        "address": 0x0221,
        "length": 1, "data_type": "int16", "access": "r", "entity": "sensor",
        "scale": 0.1, "unit": "°C", "device_class": "temperature",
        "param_number": None, "default": None,
        "category": "telemetry",
    },
    {
        "key": "fault_code_1",
        "name": "Fault Code 1",
        "address": 0x0204,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": None, "device_class": None,
        "param_number": None, "default": None,
        "category": "telemetry",
        "enabled_by_default": False,
    },
    {
        "key": "fault_code_2",
        "name": "Fault Code 2",
        "address": 0x0205,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": None, "device_class": None,
        "param_number": None, "default": None,
        "category": "telemetry",
        "enabled_by_default": False,
    },
    {
        "key": "fault_code_3",
        "name": "Fault Code 3",
        "address": 0x0206,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": None, "device_class": None,
        "param_number": None, "default": None,
        "category": "telemetry",
        "enabled_by_default": False,
    },
    {
        "key": "fault_code_4",
        "name": "Fault Code 4",
        "address": 0x0207,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": None, "device_class": None,
        "param_number": None, "default": None,
        "category": "telemetry",
        "enabled_by_default": False,
    },

    # ===================================================================
    # PRODUCT INFO — read-only (0x000B–0x0020 block)
    # Confirmed via probe: reads 000B 22
    # ===================================================================

    {
        "key": "machine_type_code",
        "single_read": True,
        "name": "Machine Type Code",
        "address": 0x000B,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": None, "device_class": None,
        "param_number": None, "default": None,
        "category": "telemetry",
        "enabled_by_default": False,
        "note": "03=Inverter, 04=Integrated inverter/controller. Your unit returns 4.",
    },
    {
        "key": "cpu1_sw_version",
        "single_read": True,
        "name": "CPU1 Software Version",
        "address": 0x0014,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": None, "device_class": None,
        "param_number": None, "default": None,
        "category": "telemetry",
        "enabled_by_default": False,
        "note": "Firmware version of CPU1. Raw value e.g. 231 = V2.31.",
    },
    {
        "key": "cpu2_sw_version",
        "single_read": True,
        "name": "CPU2 Software Version",
        "address": 0x0015,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": None, "device_class": None,
        "param_number": None, "default": None,
        "category": "telemetry",
        "enabled_by_default": False,
        "note": "Firmware version of CPU2. Raw value e.g. 201 = V2.01.",
    },
    {
        "key": "hw_version_control",
        "single_read": True,
        "name": "Control Board Hardware Version",
        "address": 0x0016,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": None, "device_class": None,
        "param_number": None, "default": None,
        "category": "telemetry",
        "enabled_by_default": False,
        "note": "Hardware version of control board. Raw value e.g. 200 = V2.00.",
    },
    {
        "key": "model_code",
        "single_read": True,
        "name": "Model Code",
        "address": 0x001B,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": None, "device_class": None,
        "param_number": None, "default": None,
        "category": "telemetry",
        "enabled_by_default": False,
        "note": "Manufacturer model code. Your unit returns 34 (0x22).",
    },
    {
        "key": "protocol_version",
        "single_read": True,
        "name": "RS485 Protocol Version",
        "address": 0x001C,
        "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
        "scale": 1, "unit": None, "device_class": None,
        "param_number": None, "default": None,
        "category": "telemetry",
        "enabled_by_default": False,
        "note": "Modbus protocol version implemented by this firmware. "
                "Raw value e.g. 107 = V1.07.",
    },

    # ===================================================================
    # BATTERY CONFIG — writable (0xE0xx block)
    # ===================================================================

    {
        "key": "max_pv_charge_current",
        "name": "Max PV Charger Current",
        "address": 0xE001,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 1, "unit": "A", "device_class": "current",
        "min_value": 0, "max_value": 100, "step": 1,
        "param_number": 36, "default": 80,
        "category": "battery_config",
        "note": "Parameter [36]: Max PV charger current. Range 0~100A.",
    },
    {
        "key": "battery_type",
        "name": "Battery Type",
        "address": 0xE004,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "select",
        "scale": 1, "unit": None, "device_class": None,
        "options": BATTERY_TYPE_OPTIONS,
        "param_number": 8, "default": 3,
        "category": "battery_config",
        "note": "Parameter [08]: default is GEL. Most voltage setpoints below are "
                "only editable when battery type is User Defined or a Lithium type.",
    },
    {
        "key": "over_voltage_threshold",
        "name": "Over-voltage Disconnection Voltage",
        "address": 0xE005,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "min_value": 40, "max_value": 60, "step": 0.4,
        "param_number": None, "default": 60,
        "category": "battery_config",
        "note": "Factory default 60V for all battery types.",
    },
    {
        "key": "boost_charge_voltage",
        "name": "Boost / Constant Charge Voltage",
        "address": 0xE008,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "min_value": 48, "max_value": 58.4, "step": 0.4,
        "param_number": 9, "default": 57.6,
        "category": "battery_config",
        "note": "Parameter [09]: Boost voltage. Range 48~58.4V step 0.4V. "
                "User-defined and lithium types only.",
    },
    {
        "key": "float_charge_voltage",
        "name": "Float Charge Voltage",
        "address": 0xE009,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "min_value": 48, "max_value": 58.4, "step": 0.4,
        "param_number": 11, "default": 55.2,
        "category": "battery_config",
        "note": "Parameter [11]: Float charge voltage. Range 48~58.4V step 0.4V. "
                "May be a no-op when BMS communication is enabled (BMS governs charge curve).",
    },
    {
        "key": "battery_recharge_recovery",
        "name": "Battery Recharge Recovery Point",
        "address": 0xE022,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "min_value": 44, "max_value": 54, "step": 0.4,
        "param_number": 37, "default": 52,
        "category": "battery_config",
        "note": "Parameter [37]: After battery fully charged and charging stopped, "
                "resume charging when voltage drops below this value. Range 44~54V.",
    },
    {
        "key": "over_discharge_recovery_voltage",
        "name": "Battery Under-voltage Recovery Point",
        "address": 0xE01B,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "min_value": 44, "max_value": 54.4, "step": 0.4,
        "param_number": 35, "default": 52,
        "category": "battery_config",
        "note": "Parameter [35]: When battery is under-voltage, inverter restores AC "
                "output once battery exceeds this voltage. Range 44~54.4V.",
    },
    {
        "key": "under_voltage_warning",
        "name": "Battery Under-voltage Alarm Point",
        "address": 0xE00C,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "min_value": 40, "max_value": 52, "step": 0.4,
        "param_number": 14, "default": 44,
        "category": "battery_config",
        "note": "Parameter [14]: Alarm triggered below this voltage; output not shut down. "
                "Range 40~52V step 0.4V.",
    },
    {
        "key": "over_discharge_voltage",
        "name": "Over-discharge Voltage",
        "address": 0xE00D,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "min_value": 40, "max_value": 48, "step": 0.4,
        "param_number": 12, "default": 42,
        "category": "battery_config",
        "note": "Parameter [12]: Inverter output shut off after over-discharge delay "
                "([13]) when voltage drops below this. Range 40~48V step 0.4V.",
    },
    {
        "key": "over_discharge_delay",
        "name": "Over-discharge Delay Time",
        "address": 0xE010,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 1, "unit": "s", "device_class": None,
        "min_value": 5, "max_value": 50, "step": 5,
        "param_number": 13, "default": 5,
        "category": "battery_config",
        "note": "Parameter [13]: Delay before shutting off inverter after over-discharge "
                "voltage ([12]) is reached. Range 5~50S step 5S.",
    },
    {
        "key": "limited_discharge_voltage",
        "name": "Battery Discharge Limit Voltage",
        "address": 0xE00E,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "min_value": 40, "max_value": 52, "step": 0.4,
        "param_number": 15, "default": 40,
        "category": "battery_config",
        "note": "Parameter [15]: Immediate shutdown when voltage drops below this. "
                "User-defined and lithium types only. Range 40~52V step 0.4V.",
    },
    {
        "key": "equalizing_charge_voltage",
        "name": "Equalization Voltage",
        "address": 0xE007,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "min_value": 48, "max_value": 58, "step": 0.4,
        "param_number": 17, "default": 58,
        "category": "battery_config",
        "note": "Parameter [17]: Flooded/sealed/user-defined only. Range 48~58V step 0.4V.",
    },
    {
        "key": "boost_charge_time",
        "name": "Maximum Boost Duration",
        "address": 0xE012,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 1, "unit": "min", "device_class": None,
        "min_value": 5, "max_value": 900, "step": 5,
        "param_number": 10, "default": 120,
        "category": "battery_config",
        "note": "Parameter [10]: Max time at constant-voltage (boost) charge stage. "
                "Range 5~900min step 5min.",
    },
    {
        "key": "equalization_charge_time",
        "name": "Equalization Charging Time",
        "address": 0xE011,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 1, "unit": "min", "device_class": None,
        "min_value": 5, "max_value": 900, "step": 5,
        "param_number": 18, "default": 120,
        "category": "battery_config",
        "note": "Parameter [18]: Lead-acid and user-defined only. Range 5~900min step 5min.",
    },
    {
        "key": "equalization_charge_delay",
        "name": "Equalized Charging Delay",
        "address": 0xE013,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 1, "unit": "min", "device_class": None,
        "min_value": 5, "max_value": 900, "step": 5,
        "param_number": 19, "default": 120,
        "category": "battery_config",
        "note": "Parameter [19]: Lead-acid and user-defined only. Range 5~900min step 5min.",
    },
    {
        "key": "equalization_charge_interval",
        "name": "Equalization Charge Interval",
        "address": 0xE01A,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 1, "unit": "days", "device_class": None,
        "min_value": 0, "max_value": 30, "step": 1,
        "param_number": 20, "default": 30,
        "category": "battery_config",
        "note": "Parameter [20]: Lead-acid and user-defined only. Range 0~30d.",
    },
    {
        "key": "stop_charging_current",
        "name": "Stop Charging Current",
        "address": 0xE01C,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.1, "unit": "A", "device_class": "current",
        "min_value": 0, "max_value": 40, "step": 0.1,
        "param_number": 57, "default": 2,
        "category": "battery_config",
        "note": "Parameter [57]: Lithium only. Charging stops when constant-voltage "
                "stage current drops below this value. Default 2A.",
    },
    {
        "key": "stop_charging_soc",
        "name": "Cut-off Charge SOC Setting",
        "address": 0xE01D,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 1, "unit": "%", "device_class": None,
        "min_value": 0, "max_value": 100, "step": 1,
        "param_number": 60, "default": 100,
        "category": "battery_config",
        "note": "Parameter [60]: Charging stops when SOC reaches this value. "
                "Valid when BMS communication is normal. Default 100%.",
    },
    {
        "key": "soc_low_warning",
        "name": "Discharge Alarm SOC Setting",
        "address": 0xE01E,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 1, "unit": "%", "device_class": None,
        "min_value": 0, "max_value": 100, "step": 1,
        "param_number": 58, "default": 15,
        "category": "battery_config",
        "note": "Parameter [58]: SOC alarm when capacity falls below this value. "
                "Valid when BMS communication is normal. Default 15%.",
    },
    {
        "key": "switch_to_mains_soc",
        "name": "Switch to Mains SOC Setting",
        "address": 0xE01F,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 1, "unit": "%", "device_class": None,
        "min_value": 0, "max_value": 100, "step": 1,
        "param_number": 61, "default": 10,
        "category": "inverter_config",
        "note": "Parameter [61]: SBU mode — switch to mains when SOC drops to or below "
                "this value. Valid when BMS communication is normal. Default 10%.",
    },
    {
        "key": "switch_to_inverter_soc",
        "name": "Switch to Inverter Output SOC Setting",
        "address": 0xE020,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 1, "unit": "%", "device_class": None,
        "min_value": 1, "max_value": 100, "step": 1,
        "param_number": 62, "default": 100,
        "category": "inverter_config",
        "note": "Parameter [62]: SBU mode — switch back to inverter output when SOC "
                "rises to or above this value. Valid when BMS communication is normal. "
                "Default 100%.",
    },
    # Parameter 59 (Cut-off Discharge SOC, 5%, stops discharging) and
    # Parameter 78 (Battery Hybrid Discharge Current, 100A) are confirmed
    # in the manual but their Modbus register addresses have not been
    # found in any available protocol document. Add here once confirmed.

    # ===================================================================
    # INVERTER CONFIG — writable (0xE2xx block)
    # All addresses verified via live probe scan cross-referenced with
    # timbit123/srne-modbus (mqtt_topic_config.py) against real SRNE hardware.
    # The V1.7 protocol doc E20x addresses are factory mirror/shadow registers;
    # active runtime settings live at different offsets confirmed below.
    # ALL addresses in this section verified via live probe (change on panel,
    # observe which register changes). V1.7 doc cross-referenced for options/scales.
    # ===================================================================

    {
        "key": "output_priority",
        "name": "Output Priority",
        "address": 0xE204,
        "single_read": True,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "select",
        "scale": 1, "unit": None, "device_class": None,
        "options": {
            0: "Solar (PV First)",
            1: "Line (Utility First)",
            2: "SBU (Solar-Battery-Utility)",
        },
        "param_number": 1, "default": 0,
        "category": "inverter_config",
        "note": "What powers the loads: Solar First / Utility First / SBU. "
                "Address 0xE204 confirmed via probe (AC1ST=1, PV1ST=0). "
                "V1.7 doc: E204 Output priority, 0=solar 1=line 2=SBU.",
    },
    {
        "key": "charge_priority",
        "name": "Charging Mode / Charge Priority",
        "address": 0xE20F,
        "single_read": True,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "select",
        "scale": 1, "unit": None, "device_class": None,
        "options": {
            0: "Solar First",
            1: "Utility First",
            2: "Solar and Utility (Hybrid)",
            3: "Solar Only (PV Only)",
        },
        "param_number": 6, "default": 3,
        "category": "inverter_config",
        "note": "How the battery is charged. Address 0xE20F confirmed via probe "
                "(Hybrid=2, SolarOnly=3). Options 0 and 1 exist per V1.7 doc but "
                "your panel firmware only exposes 2 and 3. V1.7 doc: E20F Charge priority.",
    },
    {
        "key": "max_charge_current",
        "name": "Maximum Charging Current",
        "address": 0xE20A,
        "single_read": True,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.1, "unit": "A", "device_class": "current",
        "min_value": 0, "max_value": 150, "step": 0.1,
        "param_number": 7, "default": 80,
        "category": "inverter_config",
        "note": "Parameter [07]: Max total charging current (PV + mains combined). "
                "Scale 0.1 per V1.7 doc (raw=200→20.0A). Default 80A per doc.",
    },
    {
        "key": "mains_charge_current_limit",
        "name": "Grid Charge Current Limit",
        "address": 0xE205,
        "single_read": True,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.1, "unit": "A", "device_class": "current",
        "min_value": 0, "max_value": 100, "step": 0.1,
        "param_number": 28, "default": 80,
        "category": "inverter_config",
        "note": "Parameter [28]: Max grid charge current limit. "
                "Scale 0.1 per V1.7 doc (raw=20→2.0A). Default 80A per doc. "
                "Panel may show 0 when Solar Only charge mode is active "
                "(register retains last value but grid charging is suppressed).",
    },
    {
        "key": "ac_input_range",
        "name": "AC Input Voltage Range",
        "address": 0xE20B,
        "single_read": True,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "select",
        "scale": 1, "unit": None, "device_class": None,
        "options": {
            0: "Wide range (APL, 90~280V)",
            1: "Narrow range (UPS, 170~280V)",
        },
        "param_number": 3, "default": 1,
        "category": "inverter_config",
        "note": "Parameter [03]: Wide (APL) or Narrow (UPS). "
                "Options confirmed via timbit123 (Wide=0, Narrow=1). "
                "Probe shows 0xE20B=1=Narrow. V1.7 doc had this inverted.",
    },
    {
        "key": "output_voltage",
        "name": "AC Output Rated Voltage",
        "address": 0xE208,
        "single_read": True,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.1, "unit": "V", "device_class": "voltage",
        "min_value": 100, "max_value": 264, "step": 1,
        "param_number": 38, "default": 120,
        "category": "inverter_config",
        "note": "Parameter [38]: Confirmed (raw=1200→120.0V). "
                "Only settable when rocker switch is off.",
    },
    {
        "key": "output_frequency",
        "name": "Output Frequency",
        "address": 0xE209,
        "single_read": True,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "number",
        "scale": 0.01, "unit": "Hz", "device_class": "frequency",
        "min_value": 45, "max_value": 65, "step": 0.1,
        "param_number": 2, "default": 60,
        "category": "inverter_config",
        "note": "Parameter [02]: Confirmed (raw=6000→60.00Hz). "
                "Only settable when rocker switch is off.",
    },
    {
        "key": "bms_comm_enable",
        "name": "BMS Communication Enable",
        "address": 0xE215,
        "single_read": True,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "select",
        "scale": 1, "unit": None, "device_class": None,
        "options": {
            0: "Disable",
            1: "RS485",
            2: "CAN",
        },
        "param_number": None, "default": 0,
        "category": "inverter_config",
        "note": "BMS communication mode. Confirmed (0xE215=1=RS485). "
                "timbit123: BmsCommEnable (0=Disable, 1=RS485, 2=CAN). "
                "When enabled, set BMS Protocol to match your BMS.",
    },
    {
        "key": "bms_protocol",
        "name": "BMS Communication Protocol",
        "address": 0xE21B,
        "single_read": True,
        "length": 1, "data_type": "uint16", "access": "rw", "entity": "select",
        "scale": 1, "unit": None, "device_class": None,
        "options": {
            0: "PACE",
            1: "RUDA (Ritar)",
            2: "AOGUAN (AllGrand)",
            3: "OULITE (Oliter)",
            4: "CEF",
            5: "XINWANGDA (Sunwoda)",
            6: "DAQIN (Daking)",
            7: "WOW (SRNE)",
            8: "PYL (Pylontech)",
            9: "MIT",
            10: "XIX",
            11: "POL",
            12: "GUOX",
            13: "SMK",
            14: "VOL",
            15: "WES",
        },
        "param_number": 33, "default": None,
        "category": "inverter_config",
        "note": "Parameter [33]: BMS brand/protocol. "
                "Address 0xE21B and Pylontech=8 confirmed (probe raw=8, timbit123 map). "
                "Previous version used 0xE21C with Pylontech=7 — both were wrong.",
    },
    # Output priority (what powers loads), power saving, alarm enable,
    # auto-restart, bypass-on-overload, equalization enable: addresses
    # confirmed via timbit123 but not yet exposed as entities.
    # Add in a future version once entity types and options are fully validated.
]


def get_register(key: str) -> dict | None:
    """Look up a single register definition by its key."""
    for reg in REGISTERS:
        if reg["key"] == key:
            return reg
    return None


def registers_by_entity(entity_type: str) -> list[dict]:
    """Return all register definitions for a given entity platform type."""
    return [r for r in REGISTERS if r["entity"] == entity_type]
