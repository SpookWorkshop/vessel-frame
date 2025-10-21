from typing import Protocol, runtime_checkable

@runtime_checkable
class Plugin(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

