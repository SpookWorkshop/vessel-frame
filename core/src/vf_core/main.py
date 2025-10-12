from __future__ import annotations
import asyncio
import signal
import sys
from contextlib import suppress
from .message_bus import MessageBus
from .plugin_manager import PluginManager

# ---- Quick subscriber for testing message plugins work
TOPIC = "ais.raw"

async def printer(bus: MessageBus) -> None:
    async for msg in bus.subscribe(TOPIC):
        print(f"[core] received on '{TOPIC}': {msg!r}")
# ----

async def run(argv: list[str] | None = None) -> int:
    bus = MessageBus()
    pm = PluginManager(bus)

    # TODO: Indicate the message source in a config
    source = pm.create("mock_message_source", topic=TOPIC)
    await source.start()

    # Hook up the print subscriber
    printer_task = asyncio.create_task(printer(bus))

    stop_event = asyncio.Event()
    
    if sys.platform != 'win32':
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        printer_task.cancel()
        with suppress(asyncio.CancelledError):
            await printer_task
        await source.stop()
    
    return 0

def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(run(argv))
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    raise SystemExit(main())