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
        self._subs: defaultdict[str, list[asyncio.Queue[Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, message: Any) -> None:
        """
        Publish a message to all current subscribers of a topic.
        
        If a subscriber's queue is full, the oldest message is dropped to make room.
        This ensures subscribers always receive the most recent data.
        """
        async with self._lock:
            queues = list(self._subs.get(topic, []))

        for q in queues:
            if q.full():
                # Drop oldest message to make room
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                pass

    async def subscribe(self, topic: str) -> AsyncIterator[Any]:
        q: asyncio.Queue[Any] = asyncio.Queue(maxsize=1000)
        async with self._lock:
            self._subs[topic].append(q)

        try:
            while True:
                msg = await q.get()
                yield msg
        finally:
            async with self._lock:
                try:
                    self._subs[topic].remove(q)
                except (KeyError, ValueError):
                    # Safe even if topic was already cleared
                    pass

    async def shutdown(self) -> None:
        """
        Shutdown the message bus and clean up all subscriptions.
        
        Clears all subscriber queues. Subsequent unsubscribe operations
        from individual subscribers will be safely ignored.
        """
        async with self._lock:
            self._subs.clear()