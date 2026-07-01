"""Coordinators for the SRNE Inverter integration.

Two separate DataUpdateCoordinator instances:

  SrneTelemetryCoordinator  — polls 0x01xx/0x02xx registers every 30s.
    These are volatile RAM values (PV power, battery V/I, temperatures,
    fault codes) that change continuously and are safe to read rapidly.

  SrneConfigCoordinator     — polls 0xE0xx/0xE2xx registers every 3600s
    (also on startup). These are NVRAM/flash-backed settings that rarely
    change. E2xx registers are read one at a time (single_read:True in the
    profile) because some firmware versions reject multi-register reads of
    that block. If they fail, those keys are simply absent from coordinator
    data so HA shows "Unknown" — never a stale default.

Both coordinators share one SrneModbusClient but do NOT overlap in time
(HA's coordinator scheduling is single-threaded per event loop). Each
poll cycle opens a fresh TCP connection and closes it when done, so
ser2net never sees an idle connection to drop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .modbus_client import SrneModbusClient, SrneModbusError

_LOGGER = logging.getLogger(__name__)

_MAX_BLOCK_SIZE = 30   # SRNE protocol hard limit is 32; stay under with margin
_MAX_CONSECUTIVE_FAILURES = 3

TELEMETRY_SCAN_INTERVAL = 30   # seconds
CONFIG_SCAN_INTERVAL = 3600    # seconds


def _build_read_blocks(registers: list[dict]) -> list[list[dict]]:
    """Group registers into contiguous block reads.

    Registers with single_read:True get their own block of exactly 1.
    All others are grouped greedily into contiguous spans up to _MAX_BLOCK_SIZE.
    """
    if not registers:
        return []

    sorted_regs = sorted(registers, key=lambda r: r["address"])
    blocks: list[list[dict]] = []
    current_block: list[dict] = []
    block_start: int = 0

    for reg in sorted_regs:
        if reg.get("single_read"):
            if current_block:
                blocks.append(current_block)
                current_block = []
            blocks.append([reg])
            continue

        if not current_block:
            current_block = [reg]
            block_start = reg["address"]
            continue

        prev_end = current_block[-1]["address"] + current_block[-1]["length"]
        span_if_added = (reg["address"] + reg["length"]) - block_start

        if reg["address"] <= prev_end and span_if_added <= _MAX_BLOCK_SIZE:
            current_block.append(reg)
        else:
            blocks.append(current_block)
            current_block = [reg]
            block_start = reg["address"]

    if current_block:
        blocks.append(current_block)

    return blocks


class SrneWriteValidationError(Exception):
    """Raised when a write value is outside the register's allowed range."""


class _SrneBaseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Shared base for both coordinators."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SrneModbusClient,
        profile,
        name: str,
        scan_interval: int,
        register_filter,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.profile = profile
        self._failure_counts: dict[str, int] = {}
        self._quarantined_keys: set[str] = set()
        self._all_registers = [
            r for r in profile.REGISTERS
            if r["access"] in ("r", "rw") and register_filter(r)
        ]
        self._rebuild_blocks()

    def _rebuild_blocks(self) -> None:
        active = [r for r in self._all_registers if r["key"] not in self._quarantined_keys]
        self._read_blocks = _build_read_blocks(active)
        _LOGGER.error(
            "SRNE %s: poll plan = %d registers, %d blocks, %d quarantined. Blocks: %s",
            self.name, len(active), len(self._read_blocks), len(self._quarantined_keys),
            [(f"0x{b[0]['address']:04X}", len(b)) for b in self._read_blocks],
        )

    @property
    def quarantined_keys(self) -> set[str]:
        return self._quarantined_keys

    async def _async_update_data(self) -> dict[str, Any]:
        _LOGGER.debug("SRNE %s: starting poll (%d blocks)", self.name, len(self._read_blocks))
        try:
            await self.client.async_connect()
        except SrneModbusError as err:
            _LOGGER.warning("SRNE %s: connect failed: %s", self.name, err)
            raise UpdateFailed(f"Could not connect: {err}") from err

        data: dict[str, Any] = {}
        block_errors: list[str] = []

        try:
            for block in self._read_blocks:
                block_start = block[0]["address"]
                block_end = block[-1]["address"] + block[-1]["length"]
                block_span = block_end - block_start
                block_keys = [r["key"] for r in block]

                try:
                    raw = await self.client.async_read_registers(block_start, block_span)
                    _LOGGER.debug("Block OK: 0x%04X keys=%s", block_start, block_keys)
                except SrneModbusError as err:
                    block_errors.append(f"0x{block_start:04X}: {err}")
                    _LOGGER.warning("SRNE block FAIL 0x%04X keys=%s: %s", block_start, block_keys, err)
                    for reg in block:
                        self._note_failure(reg["key"])
                    await asyncio.sleep(self.client.inter_block_delay)
                    continue

                for reg in block:
                    offset = reg["address"] - block_start
                    reg_raw = raw[offset: offset + reg["length"]]
                    try:
                        decoded = self.client.decode_value(reg_raw, reg["data_type"])
                        data[reg["key"]] = decoded * reg.get("scale", 1)
                        self._failure_counts[reg["key"]] = 0
                    except (ValueError, IndexError) as err:
                        block_errors.append(f"{reg['key']}: decode: {err}")
                        self._note_failure(reg["key"])

                await asyncio.sleep(self.client.inter_block_delay)

        finally:
            await self.client.async_close()

        if not data and self._read_blocks:
            raise UpdateFailed(
                f"All reads failed; errors: {'; '.join(block_errors[:3])}"
            )
        if block_errors:
            _LOGGER.warning("%s: %d block error(s): %s", self.name, len(block_errors), "; ".join(block_errors[:5]))

        return data

    def _note_failure(self, key: str) -> None:
        count = self._failure_counts.get(key, 0) + 1
        self._failure_counts[key] = count
        if count >= _MAX_CONSECUTIVE_FAILURES and key not in self._quarantined_keys:
            self._quarantined_keys.add(key)
            _LOGGER.warning("Register '%s' quarantined after %d failures", key, count)
            self._rebuild_blocks()

    async def async_write_value(self, key: str, real_value: float) -> None:
        """Validate and write a value; reconnects if needed for writes."""
        reg = next((r for r in self.profile.REGISTERS if r["key"] == key), None)
        if reg is None:
            raise SrneWriteValidationError(f"Unknown register key: {key}")
        if reg["access"] != "rw":
            raise SrneWriteValidationError(f"Register {key} is not writable")

        min_v = reg.get("min_value")
        max_v = reg.get("max_value")
        if min_v is not None and real_value < min_v:
            raise SrneWriteValidationError(f"{reg['name']}: {real_value} below minimum {min_v}")
        if max_v is not None and real_value > max_v:
            raise SrneWriteValidationError(f"{reg['name']}: {real_value} above maximum {max_v}")
        if "options" in reg and int(real_value) not in reg["options"]:
            raise SrneWriteValidationError(f"{reg['name']}: {real_value} not a valid option")

        scale = reg.get("scale", 1)
        raw_value = round(real_value / scale)
        encoded = self.client.encode_value(raw_value, reg["data_type"])
        if len(encoded) != 1:
            raise SrneWriteValidationError(f"{reg['name']}: multi-register writes not implemented")

        await self.client.async_write_register(reg["address"], encoded[0])

        # Optimistically update local cache
        if self.data is not None:
            self.data[key] = real_value
            self.async_set_updated_data(self.data)


class SrneTelemetryCoordinator(_SrneBaseCoordinator):
    """Polls 0x01xx/0x02xx telemetry registers every 30 seconds."""

    def __init__(self, hass, client, profile, scan_interval=TELEMETRY_SCAN_INTERVAL):
        super().__init__(
            hass, client, profile,
            name="srne_telemetry",
            scan_interval=scan_interval,
            register_filter=lambda r: r["address"] < 0x1000,
        )


class SrneConfigCoordinator(_SrneBaseCoordinator):
    """Polls E0xx/E2xx config registers every hour (also on startup)."""

    def __init__(self, hass, client, profile, scan_interval=CONFIG_SCAN_INTERVAL):
        super().__init__(
            hass, client, profile,
            name="srne_config",
            scan_interval=scan_interval,
            register_filter=lambda r: r["address"] >= 0xE000,
        )


# Keep a combined coordinator alias used by the quarantine sensor
SrneInverterCoordinator = SrneTelemetryCoordinator
