"""Profile registry.

A profile defines the register map and parameter list for one SRNE product
family. To add support for another model:
  1. Create parameter_map_<model>.csv alongside the existing parameter_map.csv
  2. Create srne_<model>.py that points csv_loader at that CSV file
  3. Register it in PROFILES below
"""

from __future__ import annotations

from . import srne_hyp_hyp4850

PROFILES: dict[str, object] = {
    srne_hyp_hyp4850.PROFILE_ID: srne_hyp_hyp4850,
}

DEFAULT_PROFILE_ID = srne_hyp_hyp4850.PROFILE_ID


def get_profile(profile_id: str):
    return PROFILES.get(profile_id, PROFILES[DEFAULT_PROFILE_ID])


def profile_choices() -> dict[str, str]:
    return {pid: mod.PROFILE_NAME for pid, mod in PROFILES.items()}
