"""DataUpdateCoordinator for the SRNE Inverter integration.

Polls every readable register defined in the active profile on each update
interval, and exposes a single async_write_value() entry point that all
writable entities (number/select) call through. Range validation against
the profile's min_value/max_value lives here, as a second guard behind
whatever bounds the entity itself enforces in the HA UI — so a write can't
slip through some other path (e.g. a service call) without being checked.

Reads are grouped into contiguous block reads (one Modbus transaction
covering a run of adjacent registers) rather than one transaction per
register. The original per-register implementation issued 50+ separate
round-trips per poll cycle; on a real RTU-over-TCP link with retries, that
adds up to minutes per cycle and looks like a stuck "Initializing" state.
The wills106/homeassistant-solax-modbus SRNE plugin — independently
confirmed to talk to this same hardware reliably — uses block reads
(block_size=100) for exactly this reason.

Registers that consistently fail are "quarantined": after
_MAX_CONSECUTIVE_FAILURES failed attempts, a register is excluded from
future block-read ranges (it still appears as a candidate, just skipped)
so one bad/unsupported address doesn't repeatedly poison reads of its
neighbors. This mirrors the behavior of solax_modbus's
auto_block_ignore_readerror, which the user observed quarantining two
unknown registers in practice.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .modbus_client import SrneModbusClient, SrneModbusError

_LOGGER = logging.getLogger(__name__)

# Maximum number of registers to request in a single Modbus transaction.
# The SRNE protocol doc states up to 20 registers can be read at once;
# kept deliberately below that documented ceiling rather than at it, since
# "the doc says 20 works" and "this specific firmware/bridge actually
# accepts 20 reliably" are different claims, and erring smaller costs
# little (more transactions) versus erring larger (more retries/quarantine
# churn from a request the device silently can't fulfill).
_MAX_BLOCK_SIZE = 16

# After this many consecutive failures, stop attempting to read a register
# until the integration reloads. Prevents one bad address from repeatedly
# breaking the block read that contains it.
_MAX_CONSECUTIVE_FAILURES = 3


def _build_read_blocks(registers: list[dict]) -> list[list[dict]]:
    """Group registers into contiguous (or near-contiguous) block reads.

    Registers are sorted by address, then greedily grouped: a new register
    joins the current block if it's adjacent to (or overlaps slightly with
    rounding of) the previous register's end address, and the block hasn't
    exceeded _MAX_BLOCK_SIZE registers of span. Otherwise it starts a new
    block. This keeps each Modbus transaction to one contiguous address
    range, which is what read_holding_registers actually requires — you
    can't request two disjoint ranges in one call.
    """
    if not registers:
        return []

    sorted_regs = sorted(registers, key=lambda r: r["address"])
    blocks: list[list[dict]] = []
    current_block: list[dict] = [sorted_regs[0]]
    block_start = sorted_regs[0]["address"]

    for reg in sorted_regs[1:]:
        prev = current_block[-1]
        prev_end = prev["address"] + prev["length"]
        span_if_added = (reg["address"] + reg["length"]) - block_start

        if reg["address"] <= prev_end and span_if_added <= _MAX_BLOCK_SIZE:
            current_block.append(reg)
        else:
            blocks.append(current_block)
            current_block = [reg]
            block_start = reg["address"]

    blocks.append(current_block)
    return blocks


class SrneWriteValidationError(Exception):
    """Raised when a requested write value falls outside the register's allowed range."""


class SrneInverterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinates Modbus polling for one SRNE inverter/charger."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SrneModbusClient,
        profile,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="srne_inverter",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.profile = profile
        # Registers with poll:False are excluded from the regular poll cycle.
        # This covers E2xx inverter-config registers that many SRNE firmware
        # versions return permission errors on when read repeatedly, causing
        # the retry loop symptom. Those entities still exist and can be written
        # to; they just won't show a current value until the device volunteers it.
        self._all_readable_registers = [
            r for r in profile.REGISTERS
            if r["access"] in ("r", "rw") and r.get("poll", True)
        ]
        # key -> consecutive failure count. Once a key hits
        # _MAX_CONSECUTIVE_FAILURES it's excluded from _active_registers
        # (quarantined) until reload.
        self._failure_counts: dict[str, int] = {}
        self._quarantined_keys: set[str] = set()
        self._rebuild_blocks()

    def _rebuild_blocks(self) -> None:
        """Recompute read blocks from the currently non-quarantined registers."""
        active = [
            r
            for r in self._all_readable_registers
            if r["key"] not in self._quarantined_keys
        ]
        self._read_blocks = _build_read_blocks(active)
        _LOGGER.debug(
            "Rebuilt read plan: %d registers across %d block(s) (%d quarantined)",
            len(active),
            len(self._read_blocks),
            len(self._quarantined_keys),
        )

    @property
    def quarantined_keys(self) -> set[str]:
        """Register keys that have been excluded after repeated read failures."""
        return self._quarantined_keys

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll all readable registers, in contiguous blocks, and return {key: decoded_value}."""
        data: dict[str, Any] = {}
        block_errors: list[str] = []

        for block in self._read_blocks:
            block_start = block[0]["address"]
            block_end = block[-1]["address"] + block[-1]["length"]
            block_span = block_end - block_start
            block_keys = [r["key"] for r in block]

            try:
                raw = await self.client.async_read_registers(block_start, block_span)
                _LOGGER.debug(
                    "Block read OK: 0x%04X-0x%04X (%d regs, keys=%s)",
                    block_start,
                    block_end,
                    block_span,
                    block_keys,
                )
            except SrneModbusError as err:
                block_errors.append(
                    f"block 0x{block_start:04X}-0x{block_end:04X} ({block_keys}): {err}"
                )
                _LOGGER.debug(
                    "Block read FAILED: 0x%04X-0x%04X (%d regs, keys=%s): %s",
                    block_start,
                    block_end,
                    block_span,
                    block_keys,
                    err,
                )
                for reg in block:
                    self._note_failure(reg["key"])
                continue

            for reg in block:
                offset = reg["address"] - block_start
                reg_raw = raw[offset : offset + reg["length"]]
                try:
                    decoded = self.client.decode_value(reg_raw, reg["data_type"])
                    data[reg["key"]] = decoded * reg.get("scale", 1)
                    self._failure_counts[reg["key"]] = 0
                except (ValueError, IndexError) as err:
                    block_errors.append(f"{reg['key']}: decode failed: {err}")
                    _LOGGER.debug("Decode failed for %s: %s", reg["key"], err)
                    self._note_failure(reg["key"])

        if not data:
            raise UpdateFailed(
                f"All register reads failed this cycle; "
                f"{len(block_errors)} block error(s), first: "
                f"{block_errors[0] if block_errors else 'unknown'}"
            )
        if block_errors:
            _LOGGER.warning(
                "%d of %d block(s) had errors this poll cycle: %s",
                len(block_errors),
                len(self._read_blocks),
                "; ".join(block_errors[:5]),
            )

        return data

    def _note_failure(self, key: str) -> None:
        """Track a read/decode failure for one register key; quarantine if persistent."""
        count = self._failure_counts.get(key, 0) + 1
        self._failure_counts[key] = count
        if count >= _MAX_CONSECUTIVE_FAILURES and key not in self._quarantined_keys:
            self._quarantined_keys.add(key)
            _LOGGER.warning(
                "Register '%s' failed %d consecutive times — quarantining it "
                "(excluding from future reads until integration reload). "
                "If this is a register you need, check Settings > Devices & "
                "Services > SRNE Inverter > Diagnostics for details, or "
                "reload the integration to retry it.",
                key,
                count,
            )
            self._rebuild_blocks()

    async def async_write_value(self, key: str, real_value: float) -> None:
        """Validate and write a real-world value to the register identified by key.

        Raises SrneWriteValidationError if out of range, or SrneModbusError
        if the write itself fails at the transport/device level.
        """
        reg = next((r for r in self.profile.REGISTERS if r["key"] == key), None)
        if reg is None:
            raise SrneWriteValidationError(f"Unknown register key: {key}")
        if reg["access"] != "rw":
            raise SrneWriteValidationError(f"Register {key} is not writable")

        min_v = reg.get("min_value")
        max_v = reg.get("max_value")
        if min_v is not None and real_value < min_v:
            raise SrneWriteValidationError(
                f"{reg['name']}: {real_value} is below minimum {min_v}"
            )
        if max_v is not None and real_value > max_v:
            raise SrneWriteValidationError(
                f"{reg['name']}: {real_value} is above maximum {max_v}"
            )
        if "options" in reg and int(real_value) not in reg["options"]:
            raise SrneWriteValidationError(
                f"{reg['name']}: {real_value} is not a valid option"
            )

        scale = reg.get("scale", 1)
        raw_value = round(real_value / scale)
        encoded = self.client.encode_value(raw_value, reg["data_type"])

        if len(encoded) == 1:
            await self.client.async_write_register(reg["address"], encoded[0])
        else:
            # Multi-register writes aren't needed by any current profile
            # entries (all rw registers here are single-word), but guarded
            # explicitly so a future 32-bit writable register doesn't
            # silently write only the first word.
            raise SrneWriteValidationError(
                f"{reg['name']}: multi-register writes not yet implemented"
            )

        # Optimistically update local cache so the UI reflects the change
        # immediately rather than waiting for the next poll interval.
        if self.data is not None:
            self.data[key] = real_value
            self.async_set_updated_data(self.data)
