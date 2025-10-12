import asyncio
from collections import defaultdict
from typing import Any, AsyncIterator

class MessageBus:
    """
    Message Event Bus allowing topic publish and subscribe.
    Any topic can be published and subscribed by multiple components.
    Multiple subscribers to one topic will receive the event in an unpredictable order.
    """

    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue[Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, message: Any) -> None:
        async with self._lock:
            queues = list(self._subs.get(topic, []))

        for q in queues:
            q.put_nowait(message)

    async def subscribe(self, topic: str) -> AsyncIterator[Any]:
        q: asyncio.Queue[Any] = asyncio.Queue()
        async with self._lock:
            self._subs[topic].append(q)

        try:
            while True:
                msg = await q.get()
                yield msg
        finally:
            async with self._lock:
                self._subs[topic].remove(q)