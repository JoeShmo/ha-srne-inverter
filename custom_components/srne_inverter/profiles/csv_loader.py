"""CSV parameter map loader.

Reads a parameter_map CSV and builds register definitions for the integration.

CSV columns: param_number, param_name, default_value, options_or_range,
             modbus_address, scale

Rows with no modbus_address are not exposed as HA entities but are available
for reference via ALL_PARAMETERS.

The options_or_range column accepts:
  - Enum options:  "Label A=0,Label B=1,Label C=2"
  - Numeric range: "0~100 step 5"  or  "40~60"
  - Empty:         free-form or unknown
"""

from __future__ import annotations

import csv
import os
import re

# Parameters that should be read-only in HA even though the register is writable
# (e.g. AC Output Mode — only settable with the rocker switch physically off)
READ_ONLY_PARAMS = {31}


def _parse_options(options_str: str) -> dict[int, str] | None:
    """Parse 'Label=0,Label=1' into {raw_int: label}. Returns None if not an enum."""
    if not options_str or "~" in options_str:
        return None
    result = {}
    for part in options_str.split(","):
        part = part.strip()
        if "=" in part:
            label, _, raw = part.rpartition("=")
            try:
                result[int(raw.strip())] = label.strip()
            except ValueError:
                pass
    return result if result else None


def _parse_default(default_str: str, options: dict | None) -> float | int | None:
    """Parse default value string into a Python number."""
    s = re.sub(r'[AVHzmin%sdayskW°]', '', default_str).strip()
    if not s:
        return None
    # Match against option labels first
    if options:
        for raw, label in options.items():
            if default_str.strip().lower() in label.lower() or label.lower() in default_str.strip().lower():
                return raw
    try:
        return float(s)
    except ValueError:
        return None


def _parse_range(options_str: str, scale: float) -> tuple[float, float, float]:
    """Extract min, max, step from a range string like '0~100 step 5'."""
    m = re.search(r'([\d.]+)\s*~\s*([\d.]+)', options_str)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        step_m = re.search(r'step\s*([\d.]+)', options_str, re.IGNORECASE)
        step = float(step_m.group(1)) if step_m else scale
        return lo, hi, step
    return 0.0, 65535.0 * scale, scale


def _infer_unit(options_str: str, name: str) -> str | None:
    name_l = name.lower()
    if "voltage" in name_l:
        return "V"
    if "current" in name_l:
        return "A"
    if "frequency" in name_l:
        return "Hz"
    if "soc" in name_l or "%" in options_str:
        return "%"
    if "duration" in name_l or "time" in name_l or "delay" in name_l:
        if "min" in options_str:
            return "min"
        if re.search(r'\d+s', options_str):
            return "s"
    if "interval" in name_l and "day" in options_str:
        return "days"
    return None


def _infer_device_class(name: str) -> str | None:
    name_l = name.lower()
    if "voltage" in name_l:
        return "voltage"
    if "current" in name_l:
        return "current"
    if "frequency" in name_l:
        return "frequency"
    return None


def _make_key(name: str) -> str:
    """Build a stable entity key from the parameter name."""
    key = name.lower()
    for ch in ' -/(),.:':
        key = key.replace(ch, '_')
    key = re.sub(r'_+', '_', key).strip('_')
    return key[:40]


def load_parameters(csv_path: str) -> tuple[list[dict], list[dict]]:
    """Load CSV and return (registers_for_ha, all_parameters).

    registers_for_ha: register dicts ready for use in REGISTERS
    all_parameters:   all rows, including those without a modbus address
    """
    registers: list[dict] = []
    all_params: list[dict] = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            param_num = int(row["param_number"])
            name = row["param_name"].strip()
            default_str = (row.get("default_value") or "").strip()
            options_str = (row.get("options_or_range") or "").strip()
            addr_str = (row.get("modbus_address") or "").strip()
            scale_str = (row.get("scale") or "1").strip()

            scale = float(scale_str) if scale_str else 1.0
            options = _parse_options(options_str)
            default = _parse_default(default_str, options)

            all_params.append({
                "param_number": param_num,
                "name": name,
                "default": default,
                "options": options,
                "options_str": options_str,
                "addr_str": addr_str,
                "scale": scale,
            })

            # Skip rows without a modbus address
            if not addr_str:
                continue
            try:
                address = int(addr_str, 16)
            except ValueError:
                continue

            read_only = param_num in READ_ONLY_PARAMS

            if options is not None:
                entity = "sensor" if read_only else "select"
            else:
                entity = "sensor" if read_only else "number"

            reg: dict = {
                "key": _make_key(name),
                "name": name,
                "address": address,
                "length": 1,
                "data_type": "uint16",
                "access": "r" if read_only else "rw",
                "entity": entity,
                "scale": scale,
                "unit": _infer_unit(options_str, name),
                "device_class": _infer_device_class(name),
                "param_number": param_num,
                "default": default,
                "single_read": address >= 0xE200,
                "enabled_by_default": True,
            }

            if entity in ("select", "sensor") and options:
                reg["options"] = options
            if entity == "number":
                reg["min_value"], reg["max_value"], reg["step"] = _parse_range(options_str, scale)

            registers.append(reg)

    return registers, all_params
