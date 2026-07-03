# SRNE Inverter — Home Assistant Custom Integration

A Home Assistant custom integration for SRNE HYP-series hybrid inverter/chargers
and rebrands (Sungold SPH series). Exposes live telemetry as sensors and writable
configuration parameters as controls, all under a single Device page.

## **Live Modbus probe testing** (`srne_probe.py`) against a real HYP4850U100-H unit.
 csv`.

2. **HYP4850S+U100-H User Manual V2.6** (2025-04-11), Section 3.2 Setup Parameters.
 Source for parameter numbers, names, defaults, and option labels.
 https://www.srnesolar.us/userfiles/files/2025/05/09/HYP4850S+U100-H(NG+SUB)_Manual_EN_V2.6[20250411].pdf

3. **SRNE MODBUS Protocol V3.9** (standalone MPPT charge controller family — ML/MT series).
 Authoritative for the `0x000A`–`0x001A` product info block and `0x01xx`/`0x02xx`
 telemetry block structures, which are consistent across SRNE product lines.
 https://solar-thailand.co.th/pdf/SRNE-MODBUS.pdf
 *Note: this document covers standalone charge controllers, NOT the HYP hybrid
 inverter/charger. The E0xx/E2xx configuration register map in this document
 does NOT apply to the HYP family.*

4. **SRNE Energy Storage Inverter MODBUS Communication Protocol** (V1.7 or V1.92/V1.96).
 The hybrid inverter-specific protocol covering the E0xx battery config and E2xx
 inverter config register blocks. This document exists in multiple versions.
 The V1.7 variant is hosted at:
 https://github.com/shakthisachintha/SRNE-Hybrid-Inverter-Monitor/raw/master/Resources/SRNE%20hybrid%20solar%20inverter%20MODBUS%20protocol%20V1%207.pdf
 The V1.92 variant is at:
   https://www.myhomethings.eu/wp-content/uploads/2024/04/SRNE_ModBus_Protokoll_V1.92.pdf
   A V1.93 changelog for a different product line (pure inverter) reassigned 0xE204,
   but that change does not apply to the HYP hybrid inverter/charger family.
   No V1.93+ document covering the HYP series has been located. If you find one,
   please add it to `docs/` and update this README.

## Sources explicitly NOT used as authoritative

The following were consulted but are NOT used as primary sources. 96 protocol) — a community project with
 useful context but no cited primary documentation. Some addresses conflicted
 with probe results on this hardware. Do not treat as ground truth.
- **danzelziggy/srne-solarman**, **cole8888/SRNE-Solar-Charge-Controller-Monitor**,
 **jblance/mpp-solar**, and other community repos — potentially useful for
 cross-referencing but subject to the same caveat: without a primary source
 citation, they cannot be treated as authoritative. Using community repos to
 validate other community repos creates a circular reference problem.

## Architecture

**Connection:** USB-serial on a Raspberry Pi → `ser2net` → Modbus RTU-over-TCP → HA.

**Two poll loops:**
- Telemetry (battery, PV, grid, load, temperatures, faults): every 30 seconds
- Configuration parameters (E0xx/E2xx registers): every 60 minutes + on startup

**Parameter map:** `parameter_map.csv` is the authoritative source of parameter
definitions. 7 doc, independently corroborated
- ` ` — address from V1.7 doc only
- ` ` — parameter exists in manual; address not yet found; not exposed in HA

## Adding support for another model

1. Copy `parameter_map.csv` to `parameter_map_<model>.csv`
2. Update addresses and confidence levels for the new model
3. Create `profiles/srne_<model>.py` pointing `csv_loader` at the new CSV
4. Register the new profile in `profiles/__init__.py`

## Installation via HACS

1. HACS → ⋮ → Custom repositories → add this repo URL → Integration
2. Install "SRNE Inverter" from HACS
3. Restart Home Assistant
4. Settings → Devices & Services → Add Integration → "SRNE Inverter"

## ser2net setup (Raspberry Pi)

```bash
sudo apt install ser2net
# Find your device: ls -l /dev/serial/by-id/
sudo nano /etc/ser2net.yaml
```

```yaml
connection: &srne
 accepter: tcp,5020
 connector: serialdev,/dev/serial/by-id/YOUR-DEVICE-PATH,9600n81,local
 options:
 kickolduser: true
```

```bash
sudo systemctl enable --now ser2net
```