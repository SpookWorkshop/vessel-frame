from __future__ import annotations
import asyncio
from typing import Any
from contextlib import suppress
from vf_core.message_bus import MessageBus
from vf_core.plugin_types import Plugin, require_plugin_args
from pyais.queue import NMEAQueue
from pyais.stream import TagBlockQueue
import logging
from .ais_utils import get_vessel_full_type_name


class AISDecoderProcessor(Plugin):
    """
    Decode AIS messages from the bus and publish structured payloads.

    Uses `pyais` to parse incoming NMEA sentences. Incoming messages are read
    from an input topic and fed into an internal queue. A separate task
    decodes and publishes dictionaries to the output topic.
    """

    _DECODE_BATCH_SIZE: int = 10

    def __init__(
        self,
        *,
        bus: MessageBus,
        in_topic: str = "ais.raw",
        out_topic: str = "vessel.decoded",
        **kwargs: Any,
    ) -> None:
        require_plugin_args(bus=bus)
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

    def _is_valid_vessel(self, decoded: dict[str, Any]) -> bool:
        """
        Return True only if the decoded message represents a trackable ship.

        Filters base stations, navigation aids, and SAR aircraft by MMSI format.
        """
        mmsi = str(decoded.get("mmsi", ""))

        # Ship MMSI must be exactly 9 digits
        if len(mmsi) != 9:
            self._logger.debug(f"MMSI {mmsi} is not a ship, skipping.")
            return False

        # MMSI starting with 111 is a SAR aircraft
        if mmsi.startswith("111"):
            return False

        return True

    def _normalise(self, decoded: dict[str, Any]) -> dict[str, Any] | None:
        """
        Build a normalised vessel message from a decoded AIS sentence.

        Returns None if the message should be discarded (non-ship MMSI or
        message type that carries no useful information).

        The returned dict always contains 'identifier' and 'source_type'.
        If static data is present it goes in a sparse 'extension' dict containing
        the fields carried by the message. Dynamic data is inserted at the top level.
        """
        if not self._is_valid_vessel(decoded):
            return None
        mmsi = str(decoded["mmsi"])

        msg_type = decoded.get("msg_type")

        msg: dict[str, Any] = {
            "identifier":  mmsi,
            "source_type": "ais",
        }

        # Tracks which decoded keys we've explicitly handled so the
        # dynamic pass-through below doesn't duplicate them.
        handled = set(self._WITHDRAWN_FIELDS)

        if msg_type == 5:
            name = decoded.get("shipname", "")
            if isinstance(name, str):
                name = name.strip()
            if name:
                msg["name"] = name

            ship_type = decoded.get("ship_type")
            ext = {
                "imo":            decoded.get("imo"),
                "callsign":       decoded.get("callsign"),
                "ship_type":      ship_type,
                "ship_type_name": get_vessel_full_type_name(ship_type),
                "bow":            decoded.get("to_bow"),
                "stern":          decoded.get("to_stern"),
                "port":           decoded.get("to_port"),
                "starboard":      decoded.get("to_starboard"),
            }
            msg["extension"] = {k: v for k, v in ext.items() if v is not None}
            handled |= {"shipname", "imo", "callsign", "ship_type",
                        "to_bow", "to_stern", "to_port", "to_starboard"}

        elif msg_type == 24:
            part_num = decoded.get("part_num")
            handled.add("part_num")

            if part_num == 0:
                # Part A: vessel name only
                name = decoded.get("shipname", "")
                if isinstance(name, str):
                    name = name.strip()
                if name:
                    msg["name"] = name
                handled.add("shipname")

            elif part_num == 1:
                # Part B: callsign, type, dimensions, vendor
                ship_type = decoded.get("ship_type")
                ext = {
                    "callsign":       decoded.get("callsign"),
                    "ship_type":      ship_type,
                    "ship_type_name": get_vessel_full_type_name(ship_type),
                    "vendor_id":      decoded.get("vendor_id"),
                    "bow":            decoded.get("to_bow"),
                    "stern":          decoded.get("to_stern"),
                    "port":           decoded.get("to_port"),
                    "starboard":      decoded.get("to_starboard"),
                }
                ext = {k: v for k, v in ext.items() if v is not None}
                if ext:
                    msg["extension"] = ext
                handled |= {"callsign", "ship_type", "vendor_id",
                            "to_bow", "to_stern", "to_port", "to_starboard"}

        # Pass through all remaining fields as dynamic data
        for key, val in decoded.items():
            if key not in handled:
                msg[key] = val

        return msg

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
                messages_processed = 0

                while True:
                    ais_message = self._message_queue.get_or_none()

                    if not ais_message:
                        await asyncio.sleep(0.1)
                        continue

                    try:
                        decoded_sentence: dict[str, Any] = ais_message.decode().asdict()

                        msg_type = decoded_sentence.get('msg_type')
                        mmsi = decoded_sentence.get('mmsi')
                        
                        self._logger.debug(f"Decoded: Type {msg_type}, MMSI {mmsi}")

                        decoded_sentence = {
                            key: val.decode("utf-8", errors="ignore") if isinstance(val, bytes) else val
                            for key, val in decoded_sentence.items()
                        }

                        if decoded_sentence.get('msg_type') == 5:
                            decoded_sentence['ship_type_name'] = get_vessel_full_type_name(
                                decoded_sentence.get('ship_type')
                            )

                        await self._bus.publish(self._out_topic, decoded_sentence)
                    except Exception:
                        self._logger.exception("Failed decoding message")

                    messages_processed += 1

                    if messages_processed >= self._DECODE_BATCH_SIZE:
                        await asyncio.sleep(0)
                        messages_processed = 0

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
