from __future__ import annotations
import asyncio
from typing import Any
from contextlib import suppress
from vf_core.message_bus import MessageBus
from vf_core.plugin_types import Plugin
from pyais.queue import NMEAQueue
from pyais.stream import TagBlockQueue
import logging


class AISDecoderProcessor(Plugin):
    """
    Decode AIS messages from the bus and publish structured payloads.

    Uses `pyais` to parse incoming NMEA sentences. Incoming messages are read
    from an input topic and fed into an internal queue. A separate task
    decodes and publishes dictionaries to the output topic.
    """
    def __init__(
        self,
        *,
        bus: MessageBus = None,
        in_topic: str = "ais.raw",
        out_topic: str = "ais.decoded",
    ) -> None:
        if bus is None:
            raise ValueError("AIS Decoder Processor requires MessageBus")

        self._logger = logging.getLogger(__name__)

        tbq: TagBlockQueue = TagBlockQueue()

        self._bus = bus
        self._in_topic = in_topic
        self._out_topic = out_topic
        self._receive_task: asyncio.Task[None] | None = None
        self._decode_task: asyncio.Task[None] | None = None
        self._message_queue: NMEAQueue = NMEAQueue(tbq=tbq)

    async def start(self) -> None:
        """
        Start background tasks to receive and decode AIS messages.

        Safe to call multiple times.
        """
        if self._receive_task and not self._receive_task.done():
            return

        if self._decode_task and not self._decode_task.done():
            return

        self._receive_task = asyncio.create_task(self._receive_loop())
        self._decode_task = asyncio.create_task(self._decode_loop())

    async def stop(self) -> None:
        """Stop background tasks and wait for clean shutdown."""
        for task in [self._receive_task, self._decode_task]:
            if task and not task.done():
                task.cancel()

                with suppress(asyncio.CancelledError):
                    await task

    async def _receive_loop(self) -> None:
        """Receive AIS messages from the bus and enqueue them for decoding."""
        try:
            async for msg in self._bus.subscribe(self._in_topic):
                if isinstance(msg, str):
                    msg = msg.encode("utf-8")

                self._message_queue.put_line(msg)
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            self._logger.info("Receive loop cancelled")
            raise
        except Exception:
            self._logger.exception("Receive loop crashed")
            raise

    async def _decode_loop(self) -> None:
        """
        Decode queued NMEA messages and publish structured dictionaries.

        Any `bytes` values in the decoded dict are converted to UTF-8 strings
        (with errors ignored) prior to publishing on the output topic.
        """

        try:
            while True:
                ais_message = self._message_queue.get_or_none()

                if not ais_message:
                    await asyncio.sleep(0.1)
                    continue

                try:
                    decoded_sentence: dict[str, Any] = ais_message.decode().asdict()

                    for key, value in decoded_sentence.items():
                        if isinstance(value, bytes):
                            decoded_sentence[key] = value.decode(
                                "utf-8", errors="ignore"
                            )

                    await self._bus.publish(self._out_topic, decoded_sentence)
                except Exception:
                    self._logger.exception("Failed decoding message")
        except asyncio.CancelledError:
            self._logger.info("Decode loop cancelled")
            raise
        except Exception:
            self._logger.exception("Decode loop crashed")
            raise


def make_plugin(**kwargs: Any) -> Plugin:
    """
    Factory function required by the entry point.
    Receives the MessageBus from the core.
    """
    return AISDecoderProcessor(**kwargs)
