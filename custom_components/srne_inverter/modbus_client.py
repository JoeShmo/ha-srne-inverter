"""Modbus transport wrapper.

Wraps pymodbus AsyncModbusTcpClient with explicit connection lifecycle
management. The key design choice: we close and reopen the TCP connection
between every poll cycle rather than keeping a persistent connection alive.

This is necessary because ser2net (the typical ser2net bridge used with this
integration) drops idle connections and sends "Port was deleted\r\n" as an
ASCII message when it does. pymodbus receives that as garbage RTU bytes,
logs "unexpected data", and then enters a reconnect loop that floods ser2net
with rapid reconnect attempts — causing the cascade of "Cancel send, because
not connected" errors seen in practice.

By controlling the connection lifecycle ourselves (connect → poll all blocks
→ close), we ensure each poll cycle starts with a clean TCP session and
ser2net never sees an idle connection worth dropping.
"""

from __future__ import annotations

import asyncio
import logging
import struct

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

_LOGGER = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 10   # seconds to establish TCP connection
_OP_TIMEOUT = 8         # seconds per individual read/write operation
_INTER_BLOCK_DELAY = 0.1  # seconds between block reads — avoids flooding ser2net


class SrneModbusError(Exception):
    """Raised when a Modbus operation fails."""


def _resolve_rtu_framer():
    """Resolve the RTU framer argument for the installed pymodbus version."""
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
    return "rtu"


class SrneModbusClient:
    """Async Modbus client with explicit per-cycle connection management."""

    def __init__(self, host: str, port: int, slave_id: int, timeout: int = 5) -> None:
        self._host = host
        self._port = port
        self._slave_id = slave_id
        self._timeout = timeout
        self._client: AsyncModbusTcpClient | None = None

    def _make_client(self) -> AsyncModbusTcpClient:
        return AsyncModbusTcpClient(
            host=self._host,
            port=self._port,
            timeout=self._timeout,
            framer=_resolve_rtu_framer(),
            retries=1,
            reconnect_delay=0,
            reconnect_delay_max=0,
        )

    async def async_connect(self) -> None:
        """Open a fresh TCP connection. Always creates a new client instance
        so there's no state left over from a previous (possibly corrupt) session."""
        await self.async_close()
        self._client = self._make_client()
        try:
            connected = await asyncio.wait_for(
                self._client.connect(), timeout=_CONNECT_TIMEOUT
            )
        except asyncio.TimeoutError as err:
            self._client = None
            raise SrneModbusError(
                f"Timed out connecting to {self._host}:{self._port}"
            ) from err
        if not connected or not self._client.connected:
            self._client = None
            raise SrneModbusError(
                f"Could not connect to {self._host}:{self._port}"
            )
        _LOGGER.debug("Modbus TCP connected to %s:%s", self._host, self._port)

    async def async_close(self) -> None:
        """Close and discard the current client instance."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def _get_unit_kwarg(self) -> str:
        """Detect whether this pymodbus expects device_id= or slave= at runtime."""
        import inspect
        if self._client is None:
            return "slave"
        sig = inspect.signature(self._client.read_holding_registers)
        if "device_id" in sig.parameters:
            return "device_id"
        if "slave" in sig.parameters:
            return "slave"
        return "unit"

    async def _call(self, method_name: str, **kwargs):
        if self._client is None or not self._client.connected:
            raise SrneModbusError("Not connected")
        method = getattr(self._client, method_name)
        kwarg_name = self._get_unit_kwarg()
        kwargs[kwarg_name] = self._slave_id
        try:
            return await asyncio.wait_for(method(**kwargs), timeout=_OP_TIMEOUT)
        except asyncio.TimeoutError as err:
            raise SrneModbusError(
                f"Timed out waiting for response on {method_name}"
            ) from err

    async def async_read_registers(self, address: int, count: int) -> list[int]:
        """Read holding registers. Caller is responsible for ensuring connect() was called."""
        try:
            result = await self._call(
                "read_holding_registers", address=address, count=count
            )
        except ModbusException as err:
            raise SrneModbusError(
                f"Read failed at 0x{address:04X} ({count} regs): {err}"
            ) from err
        if result.isError():
            raise SrneModbusError(
                f"Device error reading 0x{address:04X} ({count} regs): {result}"
            )
        return list(result.registers)

    async def async_write_register(self, address: int, value: int) -> None:
        """Write a single holding register. Connects if not already connected."""
        if self._client is None or not self._client.connected:
            await self.async_connect()
        try:
            result = await self._call("write_register", address=address, value=value)
        except ModbusException as err:
            raise SrneModbusError(
                f"Write failed at 0x{address:04X} value={value}: {err}"
            ) from err
        if result.isError():
            raise SrneModbusError(
                f"Device error writing 0x{address:04X} value={value}: {result}"
            )

    @property
    def inter_block_delay(self) -> float:
        return _INTER_BLOCK_DELAY

    @staticmethod
    def decode_value(raw_registers: list[int], data_type: str) -> int:
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
        if data_type == "uint16":
            return [value & 0xFFFF]
        if data_type == "int16":
            return [struct.unpack(">H", struct.pack(">h", value))[0]]
        if data_type in ("uint32", "int32"):
            unsigned = value & 0xFFFFFFFF
            return [unsigned & 0xFFFF, (unsigned >> 16) & 0xFFFF]
        raise ValueError(f"Unsupported data_type: {data_type}")
