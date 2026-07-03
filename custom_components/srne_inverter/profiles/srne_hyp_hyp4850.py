"""Profile: SRNE HYP4850U100-H / Sungold SPH5048P.

Sources used:
  - HYP4850S+U100-H(NG+SUB) User Manual V2.6 (2025-04-11), Section 3.2
    https://www.srnesolar.us/userfiles/files/2025/05/09/HYP4850S+U100-H(NG+SUB)_Manual_EN_V2.6[20250411].pdf
  - SRNE Energy Storage Inverter MODBUS Communication Protocol V1.7
    (primary source for register addresses of telemetry / 0x01xx-0x02xx block)
  - Live Modbus probe testing against the actual device (for E2xx addresses,
    which the V1.7 doc describes incorrectly for this firmware version —
    the E20x range is a factory mirror block; active runtime settings are at
    higher offsets confirmed by observing which register changes when a
    setting is changed on the front panel)
  - parameter_map_v192.csv in this directory (authoritative parameter list;
    edit that file to add/correct parameters — this profile loads from it)

NOT used / explicitly rejected:
  - timbit123/srne-modbus (addresses did not match this firmware)
  - solar-thailand.co.th SRNE MODBUS PDF (standalone MPPT charge controller
    protocol, not applicable to the HYP hybrid inverter/charger family)

Address confidence levels in parameter_map_v192.csv:
  PROBE_CONFIRMED  - register address confirmed by changing setting on panel
                     and observing exactly which register changed in probe scan
  PROBE_INDIRECT   - address consistent with probe scan values but not tested
                     by changing the setting
  DOC_CONFIRMED    - address from V1.7 protocol doc, independently corroborated
  DOC_ONLY         - address from V1.7 protocol doc only, not independently verified
  UNCONFIRMED      - parameter exists in manual but register address not yet found;
                     NOT exposed as HA entity

Notes for future profiles (other SRNE models):
  - Copy this file, update PROFILE_ID/PROFILE_NAME
  - Create a matching parameter_map_<model>.csv
  - Register in profiles/__init__.py
"""

from __future__ import annotations

import os
from .csv_loader import load_parameters

PROFILE_ID = "srne_hyp4850"
PROFILE_NAME = "SRNE HYP4850U100-H / Sungold SPH5048P (and HYP series rebrands)"

DEFAULT_SLAVE_ID = 1

_CSV_PATH = os.path.join(os.path.dirname(__file__), "parameter_map_v192.csv")
_csv_registers, ALL_PARAMETERS = load_parameters(_CSV_PATH)

# ---------------------------------------------------------------------------
# Telemetry registers (read-only, live data — not in the manual parameter list
# but essential for monitoring). These come from the V1.7 protocol doc 0x01xx
# and 0x02xx blocks, confirmed working on this hardware.
# ---------------------------------------------------------------------------

_TELEMETRY = [
    # Product info (0x000B block)
    # NOTE: 0x000A on the STANDALONE controller (V3.9 doc) = system voltage (high byte)
    # and rated charging current (low byte). On the HYBRID INVERTER this register's
    # meaning is unconfirmed — the standalone doc does not apply to the hybrid family.
    # Probe result on HYP4850U100-H: raw=159 (0x009F), high=0x00, low=0x9F=159.
    # Not exposed as a sensor until meaning is confirmed from a hybrid-specific source.
    {"key": "machine_type_code", "name": "Machine Type Code", "address": 0x000B,
     "single_read": True, "length": 1, "data_type": "uint16", "access": "r",
     "entity": "sensor", "scale": 1, "unit": None, "device_class": None,
     "param_number": None, "default": None, "enabled_by_default": False,
     "note": "04=Integrated inverter/controller"},
    {"key": "cpu1_sw_version", "name": "CPU1 Software Version", "address": 0x0014,
     "single_read": True, "length": 1, "data_type": "uint16", "access": "r",
     "entity": "sensor", "scale": 1, "unit": None, "device_class": None,
     "param_number": None, "default": None, "enabled_by_default": False,
     "note": "Raw e.g. 231 = V2.31"},
    {"key": "cpu2_sw_version", "name": "CPU2 Software Version", "address": 0x0015,
     "single_read": True, "length": 1, "data_type": "uint16", "access": "r",
     "entity": "sensor", "scale": 1, "unit": None, "device_class": None,
     "param_number": None, "default": None, "enabled_by_default": False,
     "note": "Raw e.g. 201 = V2.01"},
    {"key": "hw_version_control", "name": "Control Board Hardware Version", "address": 0x0016,
     "single_read": True, "length": 1, "data_type": "uint16", "access": "r",
     "entity": "sensor", "scale": 1, "unit": None, "device_class": None,
     "param_number": None, "default": None, "enabled_by_default": False,
     "note": "Raw e.g. 200 = V2.00"},
    {"key": "model_code", "name": "Model Code", "address": 0x001B,
     "single_read": True, "length": 1, "data_type": "uint16", "access": "r",
     "entity": "sensor", "scale": 1, "unit": None, "device_class": None,
     "param_number": None, "default": None, "enabled_by_default": False,
     "note": "Manufacturer model code. HYP4850U100-H returns 34 (0x22)"},
    {"key": "protocol_version", "name": "RS485 Protocol Version", "address": 0x001C,
     "single_read": True, "length": 1, "data_type": "uint16", "access": "r",
     "entity": "sensor", "scale": 1, "unit": None, "device_class": None,
     "param_number": None, "default": None, "enabled_by_default": False,
     "note": "Raw e.g. 107 = V1.07"},
    # BMS data (0x0112-0x0117) — only available when BMS communication is active
    {"key": "bms_voltage", "name": "BMS Battery Voltage", "address": 0x0112,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "V", "device_class": "voltage",
     "param_number": None, "default": None, "enabled_by_default": True,
     "note": "BMS-reported battery voltage. Only valid when BMS communication is active."},
    {"key": "bms_current", "name": "BMS Battery Current", "address": 0x0113,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "A", "device_class": "current",
     "param_number": None, "default": None, "enabled_by_default": True,
     "note": "BMS-reported battery current. Only valid when BMS communication is active."},
    {"key": "bms_temperature", "name": "BMS Battery Temperature", "address": 0x0114,
     "length": 1, "data_type": "int16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "°C", "device_class": "temperature",
     "param_number": None, "default": None, "enabled_by_default": True,
     "note": "BMS-reported battery temperature. Only valid when BMS communication is active."},
    {"key": "bms_charge_limit_voltage", "name": "BMS Charge Limit Voltage", "address": 0x0115,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "V", "device_class": "voltage",
     "param_number": None, "default": None, "enabled_by_default": False,
     "note": "Maximum charge voltage commanded by BMS."},
    {"key": "bms_charge_limit_current", "name": "BMS Charge Limit Current", "address": 0x0116,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "A", "device_class": "current",
     "param_number": None, "default": None, "enabled_by_default": False,
     "note": "Maximum charge current commanded by BMS."},
    {"key": "bms_discharge_limit_current", "name": "BMS Discharge Limit Current", "address": 0x0117,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "A", "device_class": "current",
     "param_number": None, "default": None, "enabled_by_default": False,
     "note": "Maximum discharge current commanded by BMS."},
    # Energy statistics (0xF0xx block)
    # Confirmed via probe on HYP4850U100-H. Scale 0.1 kWh throughout.
    # Daily values reset at midnight. Lifetime values are total_increasing.
    # See docs/f0xx_register_analysis.md for full probe data and layout notes.
    {"key": "daily_pv_energy", "name": "PV Energy Today", "address": 0xF000,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "kWh", "device_class": "energy",
     "state_class": "total", "param_number": None, "default": None,
     "enabled_by_default": True,
     "note": "Daily PV generation. Resets at midnight. Use for HA Energy solar production."},
    {"key": "daily_load_energy", "name": "Load Energy Today", "address": 0xF00E,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "kWh", "device_class": "energy",
     "state_class": "total", "param_number": None, "default": None,
     "enabled_by_default": True,
     "note": "Daily load consumption. Resets at midnight. Use for HA Energy home consumption."},
    {"key": "daily_battery_charge_energy", "name": "Battery Charge Energy Today", "address": 0xF01C,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "kWh", "device_class": "energy",
     "state_class": "total", "param_number": None, "default": None,
     "enabled_by_default": True,
     "note": "Daily battery charge energy. Resets at midnight."},
    {"key": "daily_battery_discharge_energy", "name": "Battery Discharge Energy Today", "address": 0xF02D,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "kWh", "device_class": "energy",
     "state_class": "total", "param_number": None, "default": None,
     "enabled_by_default": True,
     "note": "Daily battery discharge energy. Resets at midnight."},
    {"key": "total_battery_charge_energy", "name": "Total Battery Charge Energy", "address": 0xF02A,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "kWh", "device_class": "energy",
     "state_class": "total_increasing", "param_number": None, "default": None,
     "enabled_by_default": True,
     "note": "Lifetime battery charge energy accumulator. Probe confirmed: 743.5 kWh lifetime."},
    {"key": "total_battery_discharge_energy", "name": "Total Battery Discharge Energy", "address": 0xF02B,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "kWh", "device_class": "energy",
     "state_class": "total_increasing", "param_number": None, "default": None,
     "enabled_by_default": True,
     "note": "Lifetime battery discharge energy accumulator. Probe confirmed: 588.8 kWh lifetime."},
    {"key": "total_pv_energy", "name": "Total PV Energy", "address": 0xF036,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "kWh", "device_class": "energy",
     "state_class": "total_increasing", "param_number": None, "default": None,
     "enabled_by_default": True,
     "note": "Lifetime PV generation accumulator. Probe candidate: 417.0 kWh. "
             "Confirm by checking if value grows with solar production over time."},
    {"key": "total_load_energy", "name": "Total Load Energy", "address": 0xF038,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "kWh", "device_class": "energy",
     "state_class": "total_increasing", "param_number": None, "default": None,
     "enabled_by_default": False,
     "note": "Lifetime load energy accumulator candidate. Probe value: 846.1 kWh. "
             "Disabled by default until confirmed — value seems high for load-only."},

    # Battery / PV telemetry (0x01xx)
    {"key": "battery_soc", "name": "Battery SOC", "address": 0x0100,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 1, "unit": "%", "device_class": "battery",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "battery_voltage", "name": "Battery Voltage", "address": 0x0101,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "V", "device_class": "voltage",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "battery_current", "name": "Battery Current", "address": 0x0102,
     "length": 1, "data_type": "int16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "A", "device_class": "current",
     "param_number": None, "default": None, "enabled_by_default": True,
     "note": "Signed: positive=charging, negative=discharging"},
    {"key": "device_temp_raw", "name": "Device Temperature (packed)", "address": 0x0103,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 1, "unit": None, "device_class": None,
     "param_number": None, "default": None, "enabled_by_default": False,
     "note": "High byte=controller temp C, low byte=battery temp C. Split by sensor platform."},
    {"key": "pv1_voltage", "name": "PV1 Voltage", "address": 0x0107,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "V", "device_class": "voltage",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "pv1_current", "name": "PV1 Current", "address": 0x0108,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "A", "device_class": "current",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "pv1_power", "name": "PV1 Power", "address": 0x0109,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 1, "unit": "W", "device_class": "power",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "charge_state", "name": "Charge State", "address": 0x010B,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 1, "unit": None, "device_class": "enum",
     "options": {0:"Off", 1:"Quick charge", 2:"Constant voltage", 4:"Float",
                 5:"Reserved", 6:"Li battery activate", 7:"Reserved"},
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "charge_power_total", "name": "Charge Power Total", "address": 0x010E,
     "length": 1, "data_type": "int16", "access": "r", "entity": "sensor",
     "scale": 1, "unit": "W", "device_class": "power",
     "param_number": None, "default": None, "enabled_by_default": True,
     "note": "Signed: positive=charging, negative=discharging"},
    {"key": "pv_charge_current", "name": "PV Charge Current", "address": 0x0224,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "A", "device_class": "current",
     "param_number": None, "default": None, "enabled_by_default": True},
    # Fault codes (0x02xx)
    {"key": "fault_code_1", "name": "Fault Code 1", "address": 0x0204,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 1, "unit": None, "device_class": None,
     "param_number": None, "default": None, "enabled_by_default": False},
    {"key": "fault_code_2", "name": "Fault Code 2", "address": 0x0205,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 1, "unit": None, "device_class": None,
     "param_number": None, "default": None, "enabled_by_default": False},
    {"key": "fault_code_3", "name": "Fault Code 3", "address": 0x0206,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 1, "unit": None, "device_class": None,
     "param_number": None, "default": None, "enabled_by_default": False},
    {"key": "fault_code_4", "name": "Fault Code 4", "address": 0x0207,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 1, "unit": None, "device_class": None,
     "param_number": None, "default": None, "enabled_by_default": False},
    # Machine / grid / load state (0x02xx)
    {"key": "machine_state", "name": "Machine State", "address": 0x0210,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 1, "unit": None, "device_class": "enum",
     "options": {0:"Power-up delay", 1:"Waiting", 2:"Initialization", 3:"Soft start",
                 4:"Mains powered", 5:"Inverter powered", 6:"Inverter to mains",
                 7:"Mains to inverter", 8:"Battery activate", 9:"Shutdown", 10:"Fault"},
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "bus_voltage", "name": "Bus Voltage", "address": 0x0212,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "V", "device_class": "voltage",
     "param_number": None, "default": None, "enabled_by_default": False},
    {"key": "grid_voltage", "name": "Grid Voltage", "address": 0x0213,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "V", "device_class": "voltage",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "grid_current", "name": "Grid Current", "address": 0x0214,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "A", "device_class": "current",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "grid_frequency", "name": "Grid Frequency", "address": 0x0215,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.01, "unit": "Hz", "device_class": "frequency",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "inverter_output_voltage", "name": "Inverter Output Voltage", "address": 0x0216,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "V", "device_class": "voltage",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "inverter_output_current", "name": "Inverter Output Current", "address": 0x0217,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "A", "device_class": "current",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "inverter_frequency", "name": "Inverter Frequency", "address": 0x0218,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.01, "unit": "Hz", "device_class": "frequency",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "load_current", "name": "Load Current", "address": 0x0219,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "A", "device_class": "current",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "load_active_power", "name": "Load Active Power", "address": 0x021B,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 1, "unit": "W", "device_class": "power",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "load_apparent_power", "name": "Load Apparent Power", "address": 0x021C,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 1, "unit": "VA", "device_class": "apparent_power",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "mains_charge_current_measured", "name": "Mains Charge Current (measured)",
     "address": 0x021E, "length": 1, "data_type": "uint16", "access": "r",
     "entity": "sensor", "scale": 0.1, "unit": "A", "device_class": "current",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "load_ratio", "name": "Load Ratio", "address": 0x021F,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 1, "unit": "%", "device_class": None,
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "heatsink_a_temp", "name": "Heatsink A Temperature", "address": 0x0220,
     "length": 1, "data_type": "int16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "°C", "device_class": "temperature",
     "param_number": None, "default": None, "enabled_by_default": True},
    {"key": "heatsink_b_temp", "name": "Heatsink B Temperature", "address": 0x0221,
     "length": 1, "data_type": "uint16", "access": "r", "entity": "sensor",
     "scale": 0.1, "unit": "°C", "device_class": "temperature",
     "param_number": None, "default": None, "enabled_by_default": True},
]

# Combined register list: telemetry first, then CSV-derived config registers
REGISTERS: list[dict] = _TELEMETRY + _csv_registers


def get_register(key: str) -> dict | None:
    for reg in REGISTERS:
        if reg["key"] == key:
            return reg
    return None


def registers_by_entity(entity_type: str) -> list[dict]:
    return [r for r in REGISTERS if r["entity"] == entity_type]
