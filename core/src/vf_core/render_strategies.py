import asyncio
import time
from typing import Callable, Awaitable, Any
from contextlib import suppress
import logging


class PeriodicRenderStrategy:
    """
    Enforce minimum interval between renders.
    Multiple calls to request_render during the interval period result in one render after the period ends.
    """

    def __init__(
        self,
        render_func: Callable[[], Awaitable[None]],
        min_interval: float,
    ):
        self._logger = logging.getLogger(__name__)

        self._render_func = render_func
        self._min_interval = min_interval

        self._dirty_event = asyncio.Event()

        self._task: asyncio.Task | None = None
        self._last_render_time = 0.0

    async def request_render(self) -> None:
        """
        Request a render.

        Marks the strategy as needing a render. Actual rendering is deferred and
        scheduled according to the minimum interval.
        """
        self._dirty_event.set()

    async def start(self) -> None:
        """
        Start the background loop that processes render requests.

        Safe to call multiple times; subsequent calls are no-ops while the loop
        task is already running.
        """
        if self._task and not self._task.done():
            return

        self._task = asyncio.create_task(self._state_loop())

    async def stop(self) -> None:
        """
        Stop the background loop and cancel any pending work.

        Safe to call multiple times. The method waits for the loop task to
        cancel cleanly.
        """
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _state_loop(self) -> None:
        """Internal loop that waits for requests, enforces interval and renders."""
        while True:
            try:
                # Wait for dirty flag
                await self._dirty_event.wait()

                # Enforce minimum interval before rendering
                await self._wait_for_interval()

                # We're about to render so any more events from this point
                # should trigger another render pass later
                self._dirty_event.clear()

                # Perform the render
                await self._initiate_render()
            except asyncio.CancelledError:
                raise
            except Exception:
                self._logger.exception("Render failed")

    async def _wait_for_interval(self) -> None:
        """Sleep until the minimum interval since the last render has passed."""
        current_time = time.monotonic()
        time_since_last = current_time - self._last_render_time

        if time_since_last < self._min_interval:
            remaining = self._min_interval - time_since_last
            await asyncio.sleep(remaining)

    async def _initiate_render(self) -> None:
        """Invoke the render function and update the last render timestamp."""
        await self._render_func()
        self._last_render_time = time.monotonic()


class QueuedRenderStrategy:
    """
    Enforce minimum interval between renders.
    Multiple calls to request_render during the interval period will queue requests and each will
    trigger a render after waiting for the interval to end.
    """

    def __init__(
        self,
        render_func: Callable[[Any | None], Awaitable[None]],
        min_interval: float,
    ):
        self._logger = logging.getLogger(__name__)
        self._render_func = render_func
        self._min_interval = min_interval

        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=20)

        self._task: asyncio.Task | None = None
        self._last_render_time = 0.0

    async def request_render(self, data: Any = None) -> None:
        """
        Queue a render request with optional event data.

        If the queue is full, the oldest pending request is dropped to make room.
        Ensures that render requests are processed sequentially at the configured
        interval.

        Args:
            data (Any, optional): Optional data passed to the render function.
        """
        if self._event_queue.full():
            # Drop oldest
            try:
                self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

        try:
            await self._event_queue.put_nowait(data)
        except asyncio.QueueFull:
            pass

    async def start(self) -> None:
        """
        Start the background event-processing loop.

        Safe to call multiple times; subsequent calls are no-ops while the loop
        task is already running.
        """
        if self._task and not self._task.done():
            return

        self._task = asyncio.create_task(self._event_loop())

    async def stop(self) -> None:
        """
        Stop the background event-processing loop.

        Cancels the active task and waits for it to shut down cleanly.
        Safe to call multiple times.
        """
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _event_loop(self) -> None:
        """Internal loop that processes queued render requests sequentially."""
        while True:
            try:
                # Get next event
                data = await self._event_queue.get()

                # Wait for blocking period if needed
                await self._wait_for_interval()

                # Render
                await self._initiate_render(data)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._logger.exception("Render failed")

    async def _wait_for_interval(self) -> None:
        """Sleep until the minimum interval since the last render has passed."""
        current_time = time.monotonic()
        time_since_last = current_time - self._last_render_time

        if time_since_last < self._min_interval:
            remaining = self._min_interval - time_since_last
            await asyncio.sleep(remaining)

    async def _initiate_render(self, data: Any = None) -> None:
        """Invoke the render function with optional data and update timestamp."""
        await self._render_func(data)
        self._last_render_time = time.monotonic()
