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
        Publish a message to all subscribers of a given topic.

        Ensures thread-safe access to subscriber queues. If a subscriber's queue
        is full, the oldest message is dropped to make space so that subscribers
        always receive the most recent data.

        Args:
            topic (str): The name of the topic to publish the message to.
            message (Any): The message payload to deliver to all subscribers.
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
        """
        Subscribe to a topic and receive messages as an asynchronous iterator.

        Each subscriber gets its own bounded queue (max size 1000). When a new
        message is published to the topic, it will be yielded to the subscriber.
        The subscription automatically cleans up when the iterator exits.

        Args:
            topic (str): The name of the topic to subscribe to.

        Yields:
            Any: Messages published to the specified topic in the order received.
        """
        
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
        Shut down the message bus and clear all active subscriptions.

        Removes all subscriber queues and releases resources. Any later attempts
        by existing subscribers to unsubscribe will be safely ignored.

        This method is thread-safe.
        """
        async with self._lock:
            self._subs.clear()
