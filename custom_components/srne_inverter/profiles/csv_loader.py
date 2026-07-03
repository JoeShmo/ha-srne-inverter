"""CSV-based parameter map loader.

Reads parameter_map.csv and builds register definitions for the integration.
The CSV is the single authoritative source — edit it to add/correct parameters.

Only parameters with address_confidence != UNCONFIRMED and a valid modbus_address
are exposed as HA entities. UNCONFIRMED entries are loaded into the map for
reference (e.g. by the probe tool) but are not added to REGISTERS.

This design means:
- Adding a new confirmed register = add/edit one CSV row, no Python changes needed
- The profile is portable across SRNE models that use the same protocol
- Confidence level is explicit and auditable
"""

from __future__ import annotations

import csv
import os

# Only these confidence levels produce HA entities
EXPOSE_LEVELS = {"PROBE_CONFIRMED", "PROBE_INDIRECT", "DOC_CONFIRMED", "DOC_ONLY"}

# Parameters that should be read-only in HA even if the register is writable
# (e.g. param 31 AC Output Mode — only settable with rocker switch physically off)
READ_ONLY_OVERRIDE = {31}

# Parameters whose defaults vary by battery type — don't show change indicator
BATTERY_TYPE_DEPENDENT = {9, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20, 35, 37, 57}


def _parse_options(options_str: str) -> dict[int, str] | None:
    """Parse 'KEY=val,KEY=val' option string into {raw_int: label} dict.
    Returns None if the string is empty or is a range (contains ~)."""
    if not options_str or "~" in options_str or "step" in options_str:
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
        # bare label with no = means it's a free-text list, not parseable as enum
    return result if result else None


def _parse_default(default_str: str, scale: float, options: dict | None) -> float | int | None:
    """Parse default value string into a Python number in real-world units."""
    s = default_str.strip().rstrip("AVHzmin%sdayskW").strip()
    if not s or s in ("", "ESC", "auto", "(see options)"):
        return None
    try:
        val = float(s)
        # If this is a select entity, return the raw int that matches the default label
        if options is not None:
            # find the raw value whose label contains this default string
            for raw, label in options.items():
                if default_str.strip() in label or label in default_str.strip():
                    return raw
        return val
    except ValueError:
        # Default might be a label (e.g. "GEL", "PV1ST", "SLA")
        if options:
            for raw, label in options.items():
                if default_str.strip().upper() in label.upper() or label.upper() in default_str.strip().upper():
                    return raw
        return None


def load_parameters(csv_path: str) -> tuple[list[dict], list[dict]]:
    """Load CSV and return (registers_for_ha, full_parameter_list).

    registers_for_ha: list of register dicts suitable for use in REGISTERS
    full_parameter_list: all rows including UNCONFIRMED, for reference/tooling
    """
    registers: list[dict] = []
    all_params: list[dict] = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            param_num = int(row["param_number"])
            name = row["param_name"].strip()
            default_str = row["default_value"].strip()
            options_str = row["options_or_range"].strip()
            addr_str = row["modbus_address"].strip()
            scale_str = row["scale"].strip()
            confidence = row["address_confidence"].strip()
            notes = row["notes"].strip()

            scale = float(scale_str) if scale_str else 1.0
            options = _parse_options(options_str)

            # Full param record for tooling/reference
            param = {
                "param_number": param_num,
                "name": name,
                "default_str": default_str,
                "options_str": options_str,
                "options": options,
                "addr_str": addr_str,
                "scale": scale,
                "confidence": confidence,
                "notes": notes,
            }
            all_params.append(param)

            # Skip if not exposable
            if confidence not in EXPOSE_LEVELS:
                continue
            if not addr_str or addr_str.upper() == "UNCONFIRMED":
                continue

            try:
                address = int(addr_str, 16)
            except ValueError:
                continue

            read_only = param_num in READ_ONLY_OVERRIDE
            default = _parse_default(default_str, scale, options)
            default_reliable = param_num not in BATTERY_TYPE_DEPENDENT

            # Determine entity type
            if options is not None and not read_only:
                entity = "select"
            elif options is not None and read_only:
                entity = "sensor"
            else:
                entity = "number" if not read_only else "sensor"

            reg: dict = {
                "key": f"p{param_num:02d}_{name.lower().replace(' ', '_').replace('/', '_').replace('-', '_')[:30]}",
                "name": name,
                "address": address,
                "length": 1,
                "data_type": "uint16",
                "access": "r" if read_only else "rw",
                "entity": entity,
                "scale": scale,
                "unit": _infer_unit(options_str, name),
                "device_class": _infer_device_class(options_str, name),
                "param_number": param_num,
                "default": default if default_reliable else None,
                "single_read": address >= 0xE200,  # E2xx still read one at a time
                "enabled_by_default": True,
                "note": notes if notes else None,
                "confidence": confidence,
            }

            if entity in ("number",):
                reg["min_value"], reg["max_value"], reg["step"] = _parse_range(options_str, scale)

            if entity in ("select", "sensor") and options:
                reg["options"] = options

            registers.append(reg)

    return registers, all_params


def _infer_unit(options_str: str, name: str) -> str | None:
    name_l = name.lower()
    if "voltage" in name_l or "V~" in options_str or options_str.endswith("V"):
        return "V"
    if "current" in name_l or "A~" in options_str or options_str.endswith("A"):
        return "A"
    if "frequency" in name_l or "Hz" in options_str:
        return "Hz"
    if "soc" in name_l or "%" in options_str:
        return "%"
    if "time" in name_l and "current" not in name_l:
        if "min" in options_str:
            return "min"
        if "s" in options_str and "~" in options_str:
            return "s"
        if "day" in options_str:
            return "days"
    return None


def _infer_device_class(options_str: str, name: str) -> str | None:
    name_l = name.lower()
    if "voltage" in name_l:
        return "voltage"
    if "current" in name_l:
        return "current"
    if "frequency" in name_l:
        return "frequency"
    if "temperature" in name_l:
        return "temperature"
    return None


def _parse_range(options_str: str, scale: float) -> tuple[float, float, float]:
    """Extract min, max, step from a range string like '0~100A step 5'."""
    import re
    # Try to find N~M pattern
    m = re.search(r'([\d.]+)\s*~\s*([\d.]+)', options_str)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        step_m = re.search(r'step\s*([\d.]+)', options_str, re.IGNORECASE)
        step = float(step_m.group(1)) if step_m else scale
        return lo, hi, step
    return 0, 65535 * scale, scale
