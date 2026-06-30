"""Constants for the SRNE Inverter integration."""

from __future__ import annotations

DOMAIN = "srne_inverter"

CONF_PROFILE_ID = "profile_id"
CONF_SLAVE_ID = "slave_id"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 5020
DEFAULT_SCAN_INTERVAL = 15  # seconds
DEFAULT_TIMEOUT = 5  # seconds

MANUFACTURER = "SRNE"

# Generic placeholder model name shown until a profile-specific model
# string is read from the device (P00 product-info block) in a future
# enhancement. Kept generic deliberately since this integration targets
# rebrands (e.g. Sungold) as well as SRNE-branded units.
DEFAULT_MODEL_NAME = "Energy Storage Inverter (SRNE protocol)"
