from __future__ import annotations
import asyncio
import signal
import sys
from pathlib import Path

from .plugin_types import Plugin
from .message_bus import MessageBus
from .plugin_manager import PluginManager
from .config_manager import ConfigManager

async def run(argv: list[str] | None = None) -> int:
    config_path = Path("config.toml")

    config_manager = ConfigManager(config_path)
    bus = MessageBus()
    pm = PluginManager(bus)

    try:
        config_manager.load()
    except Exception as e:
        print(f"Failed to load config from {config_path}: {e}")
        return 1

    # Track all plugins for cleanup
    sources: list[Plugin] = []
    processors: list[Plugin] = []

    # Load and start sources
    configured_sources = config_manager.get("ais-messages.sources", [])
    for s in configured_sources:
        try:
            source_config = config_manager.get(s)
            kwargs = source_config if isinstance(source_config, dict) else {}
            
            source = pm.create("vesselframe.plugins.messagesource", s, **kwargs)
            await source.start()
            sources.append(source)
            print(f"Started source: {s}")
        except Exception as e:
            print(f"Failed to start source '{s}': {e}")

    # Load and start processors
    configured_processors = config_manager.get("ais-messages.processors", [])
    for p in configured_processors:
        try:
            processor_config = config_manager.get(p)
            kwargs = processor_config if isinstance(processor_config, dict) else {}
            
            processor = pm.create("vesselframe.plugins.messageprocessors", p, **kwargs)
            await processor.start()
            processors.append(processor)
            print(f"Started processor: {p}")
        except Exception as e:
            print(f"Failed to start processor '{p}': {e}")

    if not sources:
        print("No sources started. Exiting.")
        return 1

    # Setup graceful shutdown
    stop_event = asyncio.Event()
    
    if sys.platform != 'win32':
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

    print("System running. Press Ctrl+C to stop.")
    
    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        print("\nShutdown requested...")

    # Cleanup all plugins
    print("Stopping plugins...")
    for source in sources:
        try:
            await source.stop()
        except Exception as e:
            print(f"Error stopping source: {e}")
    
    for processor in processors:
        try:
            await processor.stop()
        except Exception as e:
            print(f"Error stopping processor: {e}")
    
    print("Shutdown complete.")
    return 0

def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(run(argv))
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    raise SystemExit(main())