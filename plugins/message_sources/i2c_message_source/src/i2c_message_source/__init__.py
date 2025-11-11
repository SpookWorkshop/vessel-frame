from __future__ import annotations
import asyncio
from smbus2 import SMBus
from concurrent.futures import ThreadPoolExecutor
import logging

from typing import Any
from contextlib import suppress
from vf_core.message_bus import MessageBus
from vf_core.plugin_types import Plugin, ConfigSchema, ConfigField, ConfigFieldType


class I2CMessageSource(Plugin):
    """Source plugin that reads AIS messages from an i2c connection."""

    def __init__(
        self,
        *,
        bus: MessageBus,
        topic: str = "ais.raw",
        i2c_bus: int = 1,
        i2c_addr: int = 0x33,
        register_addr: int = 0xFF,
        block_size: int = 32,
    ) -> None:
        if bus is None:
            raise ValueError("I2C Message Source requires MessageBus")

        self._logger = logging.getLogger(__name__)
        self._bus = bus
        self._topic = topic
        self._i2c_bus = i2c_bus
        self._i2c_addr = i2c_addr
        self._block_size = block_size
        self._register_addr = register_addr
        self._i2c = None
        self._task: asyncio.Task[None] | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="i2c_ais_reader")
        self._running = False

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

    def _read_block(self) -> bytes:
        """Read a block from I2C device."""
        try:
            return bytes(self._i2c.read_i2c_block_data(
                self._i2c_addr,
                self._register_addr,
                self._block_size
            ))
        except Exception:
            self._logger.exception("Error reading from I2C")
            return b''

    async def _loop(self) -> None:
        """
        Continuously read from the i2c connection and publish messages.

        Reads lines indefinitely from i2c connection in a thread. Each valid line
        is published to the message bus.

        Logs and continues on errors.
        """
        try:
            loop = asyncio.get_event_loop()
            self._i2c = await loop.run_in_executor(
                self._executor,
                lambda: SMBus(self._i2c_bus)
            )

            self._logger.info(f"Connected to I2C bus {self._i2c_bus}, address 0x{self._i2c_addr:02X}")

            while self._running:
                # Read block in thread to avoid blocking event loop
                line = await loop.run_in_executor(self._executor, self._read_block)

                if line:
                    message = line.decode("ascii", errors="ignore").strip()
                    if message:
                        await self._bus.publish(self._topic, message)

        except Exception:
            self._logger.exception("I2C message source crashed")


def get_config_schema() -> ConfigSchema:
    """Return the config schema for this plugin.

    Defines editable fields for the admin panel.

    Returns:
        ConfigSchema: Schema describing this plugin's configuration options.
    """
    return ConfigSchema(
        plugin_name="i2c_message_source",
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
            ConfigField(
                key="register_addr",
                label="I2C Message Address",
                field_type=ConfigFieldType.STRING,
                default="0x33",
                description="I2C message address in hex format"
            ),
        ],
    )


def make_plugin(**kwargs: Any) -> Plugin:
    """
    Factory function required by the entry point.
    Receives the MessageBus from the core.
    """

    return I2CMessageSource(**kwargs)
