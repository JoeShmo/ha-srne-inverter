"""Modbus transport wrapper.

Wraps pymodbus AsyncModbusTcpClient with explicit per-cycle connection
lifecycle management and a lock to prevent the two coordinators (telemetry
and config) from overlapping on the shared connection.

Design: connect → poll all blocks → close, one TCP session per poll cycle.
This prevents ser2net from seeing idle connections (which it drops with a
"Port was deleted" ASCII message that corrupts pymodbus framing).
"""

from __future__ import annotations

import asyncio
import logging
import struct

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

_LOGGER = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 10
_OP_TIMEOUT = 8
_INTER_BLOCK_DELAY = 0.05  # 50ms quiet period between block reads


class SrneModbusError(Exception):
    """Raised when a Modbus operation fails."""


def _resolve_rtu_framer():
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
    try:
        from pymodbus.framer.rtu_framer import ModbusRtuFramer
        return ModbusRtuFramer
    except ImportError:
        pass
    return "rtu"


class SrneModbusClient:
    """Async Modbus client with per-cycle connection management."""

    def __init__(self, host: str, port: int, slave_id: int, timeout: int = 5) -> None:
        self._host = host
        self._port = port
        self._slave_id = slave_id
        self._timeout = timeout
        self._client: AsyncModbusTcpClient | None = None
        # Prevents telemetry and config coordinators from using the
        # connection simultaneously if HA happens to schedule them at the
        # same time. Lock acquired in async_connect, released in async_close.
        self._lock: asyncio.Lock = asyncio.Lock()

    def _make_client(self) -> AsyncModbusTcpClient:
        kwargs: dict = dict(
            host=self._host,
            port=self._port,
            timeout=self._timeout,
            framer=_resolve_rtu_framer(),
            retries=1,
        )
        # reconnect_delay params don't exist in older pymodbus
        try:
            return AsyncModbusTcpClient(**kwargs, reconnect_delay=0, reconnect_delay_max=0)
        except TypeError:
            return AsyncModbusTcpClient(**kwargs)

    async def async_connect(self) -> None:
        """Acquire lock and open a fresh TCP connection."""
        await self._lock.acquire()
        # If we fail to connect, release the lock so future attempts work
        try:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None

            self._client = self._make_client()
            try:
                connected = await asyncio.wait_for(
                    self._client.connect(), timeout=_CONNECT_TIMEOUT
                )
            except asyncio.TimeoutError as err:
                self._client = None
                self._lock.release()
                raise SrneModbusError(
                    f"Timed out connecting to {self._host}:{self._port}"
                ) from err

            if not connected or not self._client.connected:
                self._client = None
                self._lock.release()
                raise SrneModbusError(
                    f"Could not connect to {self._host}:{self._port}"
                )
            _LOGGER.debug("Connected to %s:%s", self._host, self._port)
        except SrneModbusError:
            raise
        except Exception as err:
            if self._lock.locked():
                self._lock.release()
            raise SrneModbusError(f"Unexpected connect error: {err}") from err

    async def async_close(self) -> None:
        """Close connection and release the lock."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        if self._lock.locked():
            self._lock.release()

    def _get_unit_kwarg(self) -> str:
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
        kwargs[self._get_unit_kwarg()] = self._slave_id
        try:
            return await asyncio.wait_for(method(**kwargs), timeout=_OP_TIMEOUT)
        except asyncio.TimeoutError as err:
            raise SrneModbusError(f"Timeout on {method_name}") from err

    async def async_read_registers(self, address: int, count: int) -> list[int]:
        try:
            result = await self._call(
                "read_holding_registers", address=address, count=count
            )
        except ModbusException as err:
            raise SrneModbusError(f"Read failed at 0x{address:04X}: {err}") from err
        if result.isError():
            raise SrneModbusError(f"Device error at 0x{address:04X}: {result}")
        return list(result.registers)

    async def async_write_register(self, address: int, value: int) -> None:
        """Write a register. Connects fresh if not already connected (for writes
        initiated outside a poll cycle, e.g. from a UI control)."""
        if self._client is None or not self._client.connected:
            await self.async_connect()
            try:
                await self._do_write(address, value)
            finally:
                await self.async_close()
        else:
            await self._do_write(address, value)

    async def _do_write(self, address: int, value: int) -> None:
        try:
            result = await self._call("write_register", address=address, value=value)
        except ModbusException as err:
            raise SrneModbusError(f"Write failed at 0x{address:04X}: {err}") from err
        if result.isError():
            raise SrneModbusError(f"Device error writing 0x{address:04X}: {result}")

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
