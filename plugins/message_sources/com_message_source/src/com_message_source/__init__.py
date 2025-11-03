from __future__ import annotations
import asyncio
import serial
from typing import Any
from contextlib import suppress
from vf_core.message_bus import MessageBus
from vf_core.plugin_types import Plugin, ConfigSchema, ConfigField, ConfigFieldType

class COMMessageSource(Plugin):
    def __init__(
        self,
        *,
        bus: MessageBus,
        topic: str = "ais.raw",
        baud: int = 38400,
        port: str = None
    ) -> None:
        if bus is None:
            raise ValueError("COM Message Source requires MessageBus")
        
        self.bus = bus
        self.topic = topic
        self.baud = baud
        self.port = port
        self.serial = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

            with suppress(asyncio.CancelledError):
                await self._task

        if self.serial is not None:
            self.serial.close()

    async def _loop(self) -> None:
        self.serial = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            timeout=1
        )

        while True:
            line = self.serial.readline()
            if line:
                message = line.decode('ascii', errors='ignore').strip()
                if message:
                    await self.bus.publish(self.topic, message)
            
            # Give other tasks a chance to run
            await asyncio.sleep(0)

def get_config_schema() -> ConfigSchema:
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
                description="Serial port name"
            ),
            ConfigField(
                key="baud_rate",
                label="Baud Rate",
                field_type=ConfigFieldType.SELECT,
                default=38400,
                options=[9600, 19200, 38400, 57600, 115200]
            )
        ]
    )

def make_plugin(**kwargs: Any) -> Plugin:
    """
    Factory function required by the entry point.
    Receives the MessageBus from the core.
    """

    return COMMessageSource(**kwargs)