from __future__ import annotations
import asyncio
from typing import Any
from contextlib import suppress
from vf_core.message_bus import MessageBus
from vf_core.plugin_types import Plugin
from pyais.queue import NMEAQueue
from pyais.stream import TagBlockQueue

class AISDecoderProcessor(Plugin):
    """
    Decoder for AIS messages using pyais
    Takes in a raw AIS message and outputs a dictionary of the data
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

        tbq: TagBlockQueue = TagBlockQueue()

        self.bus = bus
        self.in_topic = in_topic
        self.out_topic = out_topic
        self._receive_task: asyncio.Task[None] | None = None
        self._decode_task: asyncio.Task[None] | None = None
        self.message_queue: NMEAQueue = NMEAQueue(tbq=tbq)

    async def start(self) -> None:
        if self._receive_task and not self._receive_task.done():
            return
        
        if self._decode_task and not self._decode_task.done():
            return
        
        self._receive_task = asyncio.create_task(self._receive_loop())
        self._decode_task = asyncio.create_task(self._decode_loop())

    async def stop(self) -> None:
        for task in [self._receive_task, self._decode_task]:
            if task and not task.done():
                task.cancel()

                with suppress(asyncio.CancelledError):
                    await task

    async def _receive_loop(self) -> None:
        """Receive AIS messages and queues them for decoding"""
        try:
            async for msg in self.bus.subscribe(self.in_topic):
                if isinstance(msg, str):
                    msg = msg.encode('utf-8')
                
                self.message_queue.put_line(msg)
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            print("[ais_decoder_processor] Receive loop cancelled")
            raise
        except Exception as e:
            print(f"[ais_decoder_processor] Receive loop crashed: {e}")
            raise

    async def _decode_loop(self) -> None:
        """Decode previously queued messages and output over message bus"""
        try:
            while True:
                ais_message = self.message_queue.get_or_none()
                
                if not ais_message:
                    await asyncio.sleep(0.01)
                    continue

                try:
                    decoded_sentence: dict[str, Any] = ais_message.decode().asdict()
                    
                    for key, value in decoded_sentence.items():
                        if isinstance(value, bytes):
                            decoded_sentence[key] = value.decode('utf-8', errors='ignore')
                    
                    await self.bus.publish(self.out_topic, decoded_sentence)
                except Exception as e:
                    print(f"[ais_decoder_processor] Failed decoding message: {e}")
        except asyncio.CancelledError:
            print("[ais_decoder_processor] Decode loop cancelled")
            raise
        except Exception as e:
            print(f"[ais_decoder_processor] Decode loop crashed: {e}")
            raise

def make_plugin(**kwargs: Any) -> Plugin:
    """
    Factory function required by the entry point.
    Receives the MessageBus from the core.
    """

    return AISDecoderProcessor(**kwargs)