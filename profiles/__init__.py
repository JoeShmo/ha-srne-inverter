"""Profile registry.

A "profile" is a register map for one SRNE protocol family (or a rebrand
thereof). To add support for another SRNE product line later — e.g. the
standalone ML/MT charge-controller protocol, or a different firmware
revision — create a new sibling module exposing PROFILE_ID, PROFILE_NAME,
DEFAULT_SLAVE_ID, and REGISTERS (see srne_esi_v1_7.py for the shape), then
register it in PROFILES below. Nothing else in the integration needs to
change: the coordinator, entity platforms, and config flow all read from
whichever profile the user selected.
"""

from __future__ import annotations

from . import srne_esi_v1_7

PROFILES: dict[str, object] = {
    srne_esi_v1_7.PROFILE_ID: srne_esi_v1_7,
}

DEFAULT_PROFILE_ID = srne_esi_v1_7.PROFILE_ID


def get_profile(profile_id: str):
    """Return the profile module for a given profile id, or the default."""
    return PROFILES.get(profile_id, PROFILES[DEFAULT_PROFILE_ID])


def profile_choices() -> dict[str, str]:
    """Return {profile_id: profile_name} for use in the config flow selector."""
    return {pid: mod.PROFILE_NAME for pid, mod in PROFILES.items()}
