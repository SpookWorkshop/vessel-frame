import asyncio
import time
from typing import Callable, Awaitable, Any

class PeriodicRenderStrategy:
    """
    Enforce minimum interval between renders.
    Multiple calls to request_render during the interval period result in one render after the period ends.
    """

    def __init__(
        self,
        render_func: Callable[[Any | None], Awaitable[None]],
        min_interval: float,
    ):
        self._render_func = render_func
        self._min_interval = min_interval
        
        self._dirty = False
        self._dirty_event = asyncio.Event()
        
        self._task: asyncio.Task | None = None
        self._last_render_time = 0.0
    
    async def request_render(self) -> None:
        self._dirty = True
        self._dirty_event.set()
    
    async def start(self, initial_render: bool = True) -> None:
        if self._task and not self._task.done():
            return
        
        if initial_render:
            await self._initiate_render()
        
        self._task = asyncio.create_task(
            self._state_loop()
        )
    
    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
    
    async def _state_loop(self) -> None:
        while True:
            # Wait for dirty flag
            await self._dirty_event.wait()
            self._dirty_event.clear()
            
            # Wait for blocking period to pass
            await self._wait_for_interval()
            
            # Render
            if self._dirty:
                await self._initiate_render()
                self._dirty = False
    
    async def _wait_for_interval(self) -> None:
        current_time = time.time()
        time_since_last = current_time - self._last_render_time
        
        if time_since_last < self._min_interval:
            remaining = self._min_interval - time_since_last
            await asyncio.sleep(remaining)
    
    async def _initiate_render(self) -> None:
        await self._render_func()
        self._last_render_time = time.time()

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
        self._render_func = render_func
        self._min_interval = min_interval
        
        self._event_queue: asyncio.Queue = asyncio.Queue()
        
        self._task: asyncio.Task | None = None
        self._last_render_time = 0.0
    
    async def request_render(self, data: Any = None) -> None:
        """Request a render (with optional event data)"""
        await self._event_queue.put(data)
    
    async def start(self, initial_render: bool = True) -> None:
        """Start processing renders"""
        if self._task and not self._task.done():
            return
        
        if initial_render:
            await self._initiate_render(None)
        
        self._task = asyncio.create_task(
            self._event_loop()
        )
    
    async def stop(self) -> None:
        """Stop processing renders"""
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
    
    async def _event_loop(self) -> None:
        """Process queued events sequentially"""
        while True:
            # Get next event
            data = await self._event_queue.get()
            
            # Wait for blocking period if needed
            await self._wait_for_interval()
            
            # Render
            await self._initiate_render(data)
    
    async def _wait_for_interval(self) -> None:
        """Wait for minimum interval since last render"""
        current_time = time.time()
        time_since_last = current_time - self._last_render_time
        
        if time_since_last < self._min_interval:
            remaining = self._min_interval - time_since_last
            await asyncio.sleep(remaining)
    
    async def _initiate_render(self, data: Any = None) -> None:
        """Perform the actual render"""
        await self._render_func(data)
        self._last_render_time = time.time()