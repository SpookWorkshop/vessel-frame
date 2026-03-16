from __future__ import annotations
import asyncio
import serial_asyncio
import logging

from typing import Any
from contextlib import suppress
from vf_core.message_bus import MessageBus
from vf_core.plugin_types import Plugin, ConfigSchema, ConfigField, ConfigFieldType, require_plugin_args


class COMMessageSource(Plugin):
    """Source plugin that reads AIS messages from a serial COM port."""

    CONNECT_TIMEOUT: float = 10.0
    RECONNECT_DELAY: float = 5.0

    def __init__(
        self,
        *,
        bus: MessageBus,
        topic: str = "ais.raw",
        baud_rate: int = 38400,
        port: str,
        **kwargs: Any,
    ) -> None:
        require_plugin_args(bus=bus, port=port)
        self._logger = logging.getLogger(__name__)
        self._bus = bus
        self._topic = topic
        self._baud_rate = baud_rate
        self._port = port
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """
        Start the serial read loop.

        Creates a background task that continuously reads lines from the serial
        port and publishes them on the configured topic.
        """
        if self._task and not self._task.done():
            return

        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """
        Stop the serial read loop.

        Cancels the background task and waits for it to finish.
        """
        if self._task and not self._task.done():
            self._task.cancel()

            with suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        """
        Continuously read from the serial port and publish messages.

        Attempts to open the serial connection within CONNECT_TIMEOUT seconds.
        On success, reads lines indefinitely and publishes each to the message
        bus. On failure (timeout, device unplug, read error), logs the problem
        and retries after RECONNECT_DELAY seconds.
        """
        while True:
            writer = None
            try:
                self._logger.info(f"Connecting to {self._port} at {self._baud_rate} baud...")
                reader, writer = await asyncio.wait_for(
                    serial_asyncio.open_serial_connection(url=self._port, baudrate=self._baud_rate),
                    timeout=self.CONNECT_TIMEOUT,
                )
                self._logger.info(f"Connected to {self._port}")

                while True:
                    line = await reader.readline()
                    if not line:
                        self._logger.warning(f"Serial port {self._port} closed (EOF)")
                        break
                    message = line.decode("ascii", errors="ignore").strip()
                    if message:
                        await self._bus.publish(self._topic, message)
                    await asyncio.sleep(0)

            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                self._logger.warning(
                    f"Timed out connecting to {self._port}, "
                    f"retrying in {self.RECONNECT_DELAY}s"
                )
            except Exception:
                self._logger.exception(
                    f"Serial connection error on {self._port}, "
                    f"reconnecting in {self.RECONNECT_DELAY}s"
                )
            finally:
                if writer is not None:
                    with suppress(Exception):
                        writer.close()

            await asyncio.sleep(self.RECONNECT_DELAY)


def get_config_schema() -> ConfigSchema:
    """Return the config schema for this plugin.

    Defines editable fields for the admin panel.

    Returns:
        ConfigSchema: Schema describing this plugin's configuration options.
    """
    return ConfigSchema(
        plugin_name="com_message_source",
        plugin_type="source",
        fields=[
            ConfigField(
                key="port",
                label="COM Port",
                field_type=ConfigFieldType.STRING,
                default="COM3",
                required=True,
                description="Serial port name",
            ),
            ConfigField(
                key="baud_rate",
                label="Baud Rate",
                field_type=ConfigFieldType.SELECT,
                default=38400,
                options=[9600, 19200, 38400, 57600, 115200],
            ),
        ],
    )


def make_plugin(**kwargs: Any) -> Plugin:
    """
    Factory function required by the entry point.
    Receives the MessageBus from the core.
    """

    return COMMessageSource(**kwargs)
