# SRNE Inverter — Home Assistant Custom Integration

A Home Assistant custom integration for SRNE-protocol energy storage
inverter/chargers — including rebrands sold under other names (e.g. Sungold
SPH series). Built against the SRNE "Energy Storage Inverter Modbus
Communication Protocol V1.7", which covers the HYP-series hybrid
inverter/chargers (AC bypass, single MPPT stage, split-phase output).

Connects via Modbus RTU-over-TCP — typically a `ser2net` bridge on a
Raspberry Pi (or similar) that holds the physical USB-serial connection to
the inverter, letting Home Assistant itself run on a different host.

## Why this exists

Most SRNE/solar-controller Home Assistant setups either:
- use the generic `modbus:` YAML integration, which can't group entities
  into a single Device page, or
- use a register map intended for a *standalone DC charge controller*
  (ML/MT-series protocol), which doesn't match the all-in-one hybrid
  inverter/charger models that SRNE/Sungold/etc. also market as "solar
  charge controllers."

This integration targets the Energy Storage Inverter protocol specifically,
groups everything under one Device, and enforces min/max ranges from the
spec on any writable register before sending a write.

## Features

- One Device per configured inverter, with all sensors and config controls
  grouped together (Settings → Devices & Services → your inverter).
- Read-only sensors: battery, PV, grid, inverter output, load, temperatures, faults.
- Writable `number`/`select` entities for battery and inverter configuration
  (charge voltages, current limits, battery type, charge priority, BMS
  communication enable, etc.) — see the in-app entity descriptions for
  per-register notes (e.g. some battery voltage setpoints become no-ops
  once BMS communication is enabled, since the BMS then governs charging).
- Config flow (Settings → Devices & Services → Add Integration) — no YAML
  required. Validates the connection before letting you finish setup.
- Register definitions live in a separate "profile" module
  (`profiles/srne_esi_v1_7.py`), so a different SRNE protocol family or
  firmware revision can be added later as a new sibling file, selectable
  from a dropdown in the config flow, without touching the rest of the code.

## Requirements

- A working `ser2net` (or equivalent) bridge exposing the inverter's
  USB-serial connection over TCP. See `docs/ser2net-setup.md` (or your own
  notes) for that side of the setup — it's independent of this integration.
- Home Assistant 2024.1.0 or newer.

## Installation

### Via HACS (custom repository, until/unless this is added to the default store)

1. HACS → the three-dot menu (top right) → **Custom repositories**.
2. Add this repository's URL, category **Integration**.
3. Find "SRNE Inverter" in HACS and install.
4. Restart Home Assistant.
5. Settings → Devices & Services → Add Integration → search "SRNE Inverter".

### Manual

1. Copy `custom_components/srne_inverter/` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.
3. Settings → Devices & Services → Add Integration → search "SRNE Inverter".

## Configuration

All configuration happens through the UI — no YAML editing required:

| Field | Description |
|---|---|
| Name | Friendly name for the device |
| Host | IP/hostname of the ser2net bridge (e.g. your Pi) |
| Port | TCP port ser2net is listening on |
| Modbus slave ID | Usually `1` unless you've changed the inverter's address |
| Device protocol profile | Which register map to use (currently one option) |

After setup, **Settings → Devices & Services → SRNE Inverter → Configure**
lets you adjust the polling interval.

## A note on the pymodbus dependency

This integration deliberately does **not** pin a pymodbus version in its
manifest. Home Assistant's own built-in `modbus` integration depends on
pymodbus too, and that version moves often — pinning a different version
here can produce an "unsatisfiable requirements" error that breaks both
integrations at once. Instead, this integration detects which pymodbus API
shape is installed at runtime (the `framer` parameter and the `slave`/
`device_id` keyword have both changed across pymodbus releases) and adapts.

If pymodbus isn't installed at all (very unlikely — almost every HA instance
has it via the built-in `modbus` integration or another Modbus-based custom
integration), installing this integration won't pull it in automatically.
If you hit an import error for `pymodbus` specifically, enable HA's built-in
Modbus integration once (Settings → Devices & Services → Add Integration →
Modbus) to have HA install it, then this integration will be able to use it.

## Known limitations / things to verify on your hardware

- Only single-phase/split-phase registers are mapped; three-phase variant
  registers (phase B/C) are not yet included.
- Historical/statistics registers (the `F0xx` block) are not yet exposed.
- If you enable BMS Communication, some static battery voltage setpoints may
  stop having any effect, since the inverter is expected to defer those
  decisions to the BMS. This isn't independently verified against every BMS —
  test on yours and watch for unexpected behavior before relying on it.

## Contributing a new profile

To add support for another SRNE-family protocol (e.g. the standalone
ML/MT charge-controller register map):

1. Copy `profiles/srne_esi_v1_7.py` as a starting template.
2. Update `PROFILE_ID`, `PROFILE_NAME`, and the `REGISTERS` list for the new
   protocol's addresses/scaling/ranges.
3. Register the new module in `profiles/__init__.py`'s `PROFILES` dict.
4. It will automatically appear as a selectable option in the config flow.
