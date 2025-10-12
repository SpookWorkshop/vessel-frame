from collections.abc import Callable
from typing import Protocol, runtime_checkable
from .message_bus import MessageBus

@runtime_checkable
class Plugin(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

PluginFactory = Callable[[MessageBus], Plugin]