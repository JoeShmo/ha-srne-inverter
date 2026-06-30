"""Modbus transport wrapper.

This module is the only place that talks pymodbus directly. The coordinator
and entity platforms call methods on SrneModbusClient and never touch
pymodbus themselves. That separation is deliberate: today this connects over
rtuovertcp to a ser2net bridge, but if you later want a different transport
(e.g. a direct serial connection, or handing the actual polling off to an
ESPHome device and having this integration just consume the results some
other way), only this file should need to change.
"""

from __future__ import annotations

import asyncio
import logging
import struct

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

_LOGGER = logging.getLogger(__name__)

# Hard ceiling on any single operation, independent of whatever timeout
# pymodbus's own constructor argument does or doesn't enforce internally
# across versions. Without this, a TCP connection that opens but never gets
# a reply (e.g. ser2net is up but the inverter isn't answering, or a framing
# mismatch causes a silent stall) hangs forever with no error — which is
# exactly what produces an indefinitely spinning config flow UI.
_OPERATION_TIMEOUT = 10


class SrneModbusError(Exception):
    """Raised when a Modbus operation fails."""


def _resolve_rtu_framer():
    """Return whatever value this installed pymodbus expects for "RTU framing".

    pymodbus has changed this across versions:
      - older 3.x: a string, "rtu"
      - newer 3.x/4.x: pymodbus.FramerType.RTU (an enum member)
      - some 3.x point releases: pymodbus.framer.FramerType.RTU
    Home Assistant pins pymodbus independently of this integration and that
    pin has moved (and broken HA's own built-in modbus integration) more than
    once, so this resolves the correct value at runtime instead of hardcoding
    one generation's API and breaking on whichever pymodbus HA happens to
    have installed.
    """
    try:
        from pymodbus import FramerType

        return FramerType.RTU
    except ImportError:
        pass
    try:
        from pymodbus.framer import FramerType

        return FramerType.RTU
    except ImportError:
        pass
    # Fall back to the old string API for genuinely old pymodbus installs.
    return "rtu"


class SrneModbusClient:
    """Thin async wrapper around a pymodbus RTU-over-TCP client."""

    def __init__(self, host: str, port: int, slave_id: int, timeout: int = 5) -> None:
        self._host = host
        self._port = port
        self._slave_id = slave_id
        self._client = AsyncModbusTcpClient(
            host=host,
            port=port,
            timeout=timeout,
            # pymodbus retries internally (default retries=3) on top of
            # whatever retry/backoff our own coordinator does across poll
            # cycles. With block reads now reducing per-cycle transaction
            # count, we'd rather fail a block fast and let the coordinator's
            # quarantine logic handle persistent failures across cycles,
            # than wait through several seconds of internal backoff per
            # block on every single poll. Deliberately not using retries=1:
            # that exact value has a known bug in some pymodbus releases
            # (raises ModbusIOException even on a successful response).
            retries=2,
            framer=_resolve_rtu_framer(),
        )

    async def async_connect(self) -> None:
        """Open the connection if not already open."""
        if not self._client.connected:
            try:
                await asyncio.wait_for(
                    self._client.connect(), timeout=_OPERATION_TIMEOUT
                )
            except asyncio.TimeoutError as err:
                raise SrneModbusError(
                    f"Timed out connecting to {self._host}:{self._port} "
                    f"after {_OPERATION_TIMEOUT}s. Check that the ser2net "
                    f"(or equivalent) bridge is running and reachable."
                ) from err
            if not self._client.connected:
                raise SrneModbusError(
                    f"Could not connect to {self._host}:{self._port}"
                )

    async def async_close(self) -> None:
        """Close the connection."""
        self._client.close()

    def _resolve_unit_kwarg_name(self) -> str:
        """Determine whether this pymodbus expects device_id= or slave=.

        Earlier versions of this client guessed by try/except TypeError on
        the call itself, but that's unreliable: some pymodbus versions
        accept a wrong-but-similarly-named kwarg without raising TypeError
        at all (it gets swallowed or mishandled internally), which left the
        call hanging on a real network round-trip that would never resolve
        correctly — manifesting as a connection that "succeeds" but then
        spins forever with no error. Inspecting the actual method signature
        is deterministic and doesn't depend on guessing from runtime
        exceptions.
        """
        import inspect

        sig = inspect.signature(self._client.read_holding_registers)
        params = sig.parameters
        if "device_id" in params:
            return "device_id"
        if "slave" in params:
            return "slave"
        # Very old pymodbus; "unit" was the original keyword.
        return "unit"

    async def _async_call_with_unit_kwarg(self, method_name: str, **kwargs):
        """Call a pymodbus client method using whichever slave-id keyword
        this installed pymodbus version actually expects."""
        method = getattr(self._client, method_name)
        kwarg_name = self._resolve_unit_kwarg_name()
        kwargs[kwarg_name] = self._slave_id
        return await asyncio.wait_for(method(**kwargs), timeout=_OPERATION_TIMEOUT)

    async def async_read_registers(self, address: int, count: int) -> list[int]:
        """Read `count` 16-bit holding registers starting at `address`."""
        await self.async_connect()
        try:
            result = await self._async_call_with_unit_kwarg(
                "read_holding_registers", address=address, count=count
            )
        except asyncio.TimeoutError as err:
            raise SrneModbusError(
                f"Timed out reading 0x{address:04X} ({count} regs) after "
                f"{_OPERATION_TIMEOUT}s"
            ) from err
        except ModbusException as err:
            raise SrneModbusError(
                f"Read failed at 0x{address:04X} ({count} regs): {err}"
            ) from err
        if result.isError():
            raise SrneModbusError(
                f"Device returned error reading 0x{address:04X} ({count} regs): {result}"
            )
        return list(result.registers)

    async def async_write_register(self, address: int, value: int) -> None:
        """Write a single 16-bit holding register."""
        await self.async_connect()
        try:
            result = await self._async_call_with_unit_kwarg(
                "write_register", address=address, value=value
            )
        except asyncio.TimeoutError as err:
            raise SrneModbusError(
                f"Timed out writing 0x{address:04X} value={value} after "
                f"{_OPERATION_TIMEOUT}s"
            ) from err
        except ModbusException as err:
            raise SrneModbusError(
                f"Write failed at 0x{address:04X} value={value}: {err}"
            ) from err
        if result.isError():
            raise SrneModbusError(
                f"Device returned error writing 0x{address:04X} value={value}: {result}"
            )

    @staticmethod
    def decode_value(raw_registers: list[int], data_type: str) -> int:
        """Decode 1 or 2 raw 16-bit registers into a signed/unsigned int.

        32-bit values are little-endian at the register level per the SRNE
        spec (low word at the lower address), matching what pymodbus returns
        register-by-register in address order, so registers[0] is the low
        word and registers[1] is the high word for 32-bit types.
        """
        if data_type == "uint16":
            return raw_registers[0]
        if data_type == "int16":
            return struct.unpack(">h", struct.pack(">H", raw_registers[0]))[0]
        if data_type == "uint32":
            low, high = raw_registers[0], raw_registers[1]
            return (high << 16) | low
        if data_type == "int32":
            low, high = raw_registers[0], raw_registers[1]
            combined = (high << 16) | low
            return struct.unpack(">i", struct.pack(">I", combined))[0]
        raise ValueError(f"Unsupported data_type: {data_type}")

    @staticmethod
    def encode_value(value: int, data_type: str) -> list[int]:
        """Encode a signed/unsigned int into 1 or 2 raw 16-bit registers."""
        if data_type == "uint16":
            return [value & 0xFFFF]
        if data_type == "int16":
            return [struct.unpack(">H", struct.pack(">h", value))[0]]
        if data_type in ("uint32", "int32"):
            unsigned = value & 0xFFFFFFFF
            low = unsigned & 0xFFFF
            high = (unsigned >> 16) & 0xFFFF
            return [low, high]
        raise ValueError(f"Unsupported data_type: {data_type}")
