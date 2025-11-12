from __future__ import annotations
import asyncio
from smbus2 import SMBus
from concurrent.futures import ThreadPoolExecutor
import logging

from typing import Any
from contextlib import suppress
from vf_core.message_bus import MessageBus
from vf_core.plugin_types import Plugin, ConfigSchema, ConfigField, ConfigFieldType


class DaisyMessageSource(Plugin):
    """Source plugin that reads messages from a Daisy AIS device."""

    BYTES_AVAIL_H_ADDR = 0xFD
    BYTES_AVAIL_L_ADDR = 0xFE
    MESSAGE_BUFF_ADDR = 0xFF
    MAX_BLOCK_SIZE = 32
    
    def __init__(
        self,
        *,
        bus: MessageBus,
        topic: str = "ais.raw",
        i2c_bus: int | str = 1,
        i2c_addr: int | str = 0x33,
        block_size: int | str = 32,
    ) -> None:
        if bus is None:
            raise ValueError("Daisy Message Source requires MessageBus")

        self._logger = logging.getLogger(__name__)
        self._bus = bus
        self._topic = topic
        self._i2c_bus = int(i2c_bus) if isinstance(i2c_bus, str) else i2c_bus
        self._i2c_addr = self._parse_i2c_address(i2c_addr)
        self._block_size = int(block_size) if isinstance(block_size, str) else block_size
        self._i2c = None
        self._message_buffer = b""
        self._task: asyncio.Task[None] | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="i2c_ais_reader")
        self._running = False

        self._logger.info(f"Created Daisy source on bus {self._i2c_bus}, addr: {self._i2c_addr}")

    def _parse_i2c_address(self, addr: str | int) -> int:
        """Parse I2C address from hex/decimal string or int."""
        if isinstance(addr, int):
            return addr
        
        addr = addr.strip()
        if addr.startswith("0x") or addr.startswith("0X"):
            return int(addr, 16)  # Parse as hex
        else:
            return int(addr)  # Parse as decimal

    async def start(self) -> None:
        """
        Start the i2c read loop.

        Creates a background task that continuously reads i2c
        data and publishes it on the configured topic.
        """
        if self._task and not self._task.done():
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """
        Stop the i2c read loop and close the connection.

        Cancels the background task, thread and closes the i2c connection if open.
        """
        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()

            with suppress(asyncio.CancelledError):
                await self._task

        if self._i2c is not None:
            self._i2c.close()
        
        self._executor.shutdown(wait=True)

    def _read_byte(self, addr: int) -> int:
        """Read a single byte from a register."""
        try:
            self._i2c.write_byte(self._i2c_addr, addr)
            return self._i2c.read_byte(self._i2c_addr)
        except Exception:
            self._logger.exception(f"Error reading byte from register 0x{addr:02X}")
            return 0
    
    def _read_available_count(self) -> int:
        """Get number of bytes available to read."""
        try:
            high = self._read_byte(self.BYTES_AVAIL_H_ADDR)
            low = self._read_byte(self.BYTES_AVAIL_L_ADDR)
            return (high << 8) | low
        except Exception:
            self._logger.exception("Error reading available byte count")
            return 0
    
    def _read_block(self, size: int) -> bytes:
        """Read a block of specified size from I2C device."""
        try:
            buff = bytearray()
            while size > 0:
                block_size = min(size, self.MAX_BLOCK_SIZE)
                block = self._i2c.read_i2c_block_data(
                    self._i2c_addr,
                    self.MESSAGE_BUFF_ADDR,
                    block_size
                )
                buff.extend(block)
                size -= block_size
            return bytes(buff)
        except Exception:
            self._logger.exception("Error reading block from I2C")
            return b''
    
    async def _loop(self) -> None:
        """Continuously read from I2C and publish complete messages."""
        try:
            loop = asyncio.get_event_loop()
            
            # Open I2C bus
            self._i2c = await loop.run_in_executor(
                self._executor,
                lambda: SMBus(self._i2c_bus)
            )
            
            self._logger.info(f"Connected to I2C bus {self._i2c_bus}, address 0x{self._i2c_addr:02X}")
            
            # Initialize message buffer register
            await loop.run_in_executor(
                self._executor,
                lambda: self._i2c.write_byte(self._i2c_addr, self.MESSAGE_BUFF_ADDR)
            )
            
            while self._running:
                # Check how many bytes are available
                available = await loop.run_in_executor(
                    self._executor,
                    self._read_available_count
                )
                
                if available == 0:
                    # No data, wait a bit
                    await asyncio.sleep(0.05)
                    continue
                
                self._logger.debug(f"Bytes available: {available}")
                
                # Read the available bytes
                data = await loop.run_in_executor(
                    self._executor,
                    lambda: self._read_block(available)
                )
                
                if not data:
                    await asyncio.sleep(0.01)
                    continue
                
                # Add to buffer
                self._message_buffer += data
                
                # Process complete messages (ending with \r\n)
                while b"\r\n" in self._message_buffer:
                    complete, _, remainder = self._message_buffer.partition(b"\r\n")
                    
                    message = complete.decode("ascii", errors="ignore").strip()
                    if message:
                        self._logger.info(f"Message: {message}")
                        await self._bus.publish(self._topic, message)
                    
                    self._message_buffer = remainder
                
        except Exception:
            self._logger.exception("Daisy message source crashed")


def get_config_schema() -> ConfigSchema:
    """Return the config schema for this plugin.

    Defines editable fields for the admin panel.

    Returns:
        ConfigSchema: Schema describing this plugin's configuration options.
    """
    return ConfigSchema(
        plugin_name="daisy_message_source",
        plugin_type="source",
        fields=[
            ConfigField(
                key="i2c_bus",
                label="I2C Bus Number",
                field_type=ConfigFieldType.INTEGER,
                default=1,
                description="I2C bus number"
            ),
            ConfigField(
                key="i2c_addr",
                label="I2C Device Address",
                field_type=ConfigFieldType.STRING,
                default="0x33",
                description="I2C device address in hex format"
            ),
        ],
    )


def make_plugin(**kwargs: Any) -> Plugin:
    """
    Factory function required by the entry point.
    Receives the MessageBus from the core.
    """

    return DaisyMessageSource(**kwargs)
