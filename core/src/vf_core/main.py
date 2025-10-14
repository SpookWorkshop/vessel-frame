from __future__ import annotations
import asyncio
import signal
import sys
from pathlib import Path
import logging

from .plugin_types import Plugin
from .message_bus import MessageBus
from .plugin_manager import PluginManager
from .config_manager import ConfigManager
from .vessel_manager import VesselManager
from .vessel_repository import VesselRepository

async def run(argv: list[str] | None = None) -> int:
    logger:logging.Logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler('vessel_frame.log'),logging.StreamHandler()],format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",datefmt="%Y-%m-%d %H:%M:%S")

    config_path = Path("config.toml")

    config_manager = ConfigManager(config_path)
    bus = MessageBus()
    pm = PluginManager(bus)
    vessel_repo = VesselRepository("db.sqlite")
    vm = VesselManager(bus, vessel_repo, in_topic="ais.decoded")

    try:
        config_manager.load()
    except Exception as e:
        logger.exception(f"Failed to load config from {config_path}", exc_info=e)
        return 1

    # Track all plugins for cleanup
    sources: list[Plugin] = []
    processors: list[Plugin] = []

    await vm.start()

    # Load and start sources
    configured_sources = config_manager.get("ais-messages.sources", [])
    for s in configured_sources:
        try:
            source_config = config_manager.get(s)
            kwargs = source_config if isinstance(source_config, dict) else {}
            
            source = pm.create("vesselframe.plugins.messagesource", s, **kwargs)
            await source.start()
            sources.append(source)

            logger.info(f"Started source: {s}")
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
            logger.info(f"Started processor: {p}")
        except Exception as e:
            logger.exception(f"Failed to start processor '{p}'", exc_info=e)

    if not sources:
        print("No sources started. Exiting.")
        return 1

    # Setup graceful shutdown
    stop_event = asyncio.Event()
    
    if sys.platform != 'win32':
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

    logger.info("System running. Press Ctrl+C to stop.")

    try:
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        logger.info("Shutting down...")
        await vm.stop()

        # Cleanup all plugins
        logger.info("Stopping plugins...")
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
        
        logger.info("Shutdown complete.")
    return 0

def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(run(argv))
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    raise SystemExit(main())