from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any

from vf_core.message_bus import MessageBus
from vf_core.plugin_types import (
    ConfigField,
    ConfigFieldType,
    ConfigSchema,
    Plugin,
    require_plugin_args,
)


class UDPMessageSource:
    """Source plugin that receives AIS sentences over UDP."""

    def __init__(
        self,
        *,
        bus: MessageBus,
        host: str = "0.0.0.0",
        port: int = 10110,
        topic: str = "ais.raw",
        **kwargs: Any,
    ) -> None:
        require_plugin_args(bus=bus)
        self._logger = logging.getLogger(__name__)
        self._bus = bus
        self._host = host
        self._port = port
        self._topic = topic
        self._transport: asyncio.BaseTransport | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start listening for UDP datagrams."""
        if self._task and not self._task.done():
            return

        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop the UDP listener and close the socket."""
        if self._task and not self._task.done():
            self._task.cancel()

            with suppress(asyncio.CancelledError):
                await self._task

        if self._transport is not None:
            self._transport.close()

    async def _loop(self) -> None:
        """Open a UDP socket and publish received sentences to the bus."""
        try:
            loop = asyncio.get_running_loop()

            self._transport, _ = await loop.create_datagram_endpoint(
                lambda: _AISDatagramProtocol(self._bus, self._topic, self._logger),
                local_addr=(self._host, self._port),
            )

            self._logger.info(f"UDP message source listening on {self._host}:{self._port}")

            # Hold open until cancelled
            await asyncio.get_running_loop().create_future()

        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("UDP message source error")
        finally:
            if self._transport is not None:
                self._transport.close()


class _AISDatagramProtocol(asyncio.DatagramProtocol):
    """asyncio datagram protocol that publishes received AIS sentences on the bus."""

    def __init__(self, bus: MessageBus, topic: str, logger: logging.Logger) -> None:
        self._bus = bus
        self._topic = topic
        self._logger = logger
        self._loop = asyncio.get_running_loop()

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        text = data.decode("ascii", errors="ignore").strip()
        if text:
            self._loop.create_task(self._bus.publish(self._topic, text))

    def error_received(self, exc: Exception) -> None:
        self._logger.error(f"UDP error: {exc}")


def get_config_schema() -> ConfigSchema:
    return ConfigSchema(
        plugin_name="udp_message_source",
        plugin_type="source",
        fields=[
            ConfigField(
                key="host",
                label="Bind Address",
                field_type=ConfigFieldType.STRING,
                default="0.0.0.0",
                description="IP address to listen on (0.0.0.0 for all interfaces)",
            ),
            ConfigField(
                key="port",
                label="Port",
                field_type=ConfigFieldType.INTEGER,
                default=10110,
                description="UDP port to listen on",
            ),
        ],
    )


def make_plugin(**kwargs: Any) -> Plugin:
    return UDPMessageSource(**kwargs)
