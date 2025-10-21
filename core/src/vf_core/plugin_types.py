from typing import Protocol, runtime_checkable

@runtime_checkable
class Plugin(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

@runtime_checkable
class RendererPlugin(Protocol):
    def render(self) -> None: ...