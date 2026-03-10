from __future__ import annotations

import argparse
import asyncio
from contextlib import suppress
from functools import partial
import logging
import os
import signal
import sys
from pathlib import Path

from logging.handlers import RotatingFileHandler
from .plugin_types import (
    GROUP_PROCESSORS,
    GROUP_RENDERER,
    GROUP_SOURCES,
    GROUP_CONTROLLERS,
    Plugin,
    RendererPlugin,
)
from .message_bus import MessageBus
from .plugin_manager import PluginManager
from .config_manager import ConfigManager
from .vessel_manager import VesselManager
from .vessel_repository import VesselRepository
from .screen_manager import ScreenManager
from .network_manager import NetworkManager
from .asset_manager import AssetManager
from .web_admin.main import start_admin_server
from .web_admin import auth

"""
Vessel Frame

Starts core services, loads plugins, and runs the web admin.
Usage:
    vf --config config.toml --db db.sqlite --log-level INFO
"""


def _default_data_dir() -> Path:
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "vessel-frame"
        return Path.home() / "AppData" / "Local" / "vessel-frame"
    return Path("/var/lib/vessel-frame")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv (list[str] | None): Optional list of arguments. If None, uses sys.argv.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(prog="vessel-frame")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--db", type=Path, default=Path("db.sqlite"))
    parser.add_argument("--data-dir", type=Path, default=_default_data_dir())
    parser.add_argument("--log-level", default="INFO", help="DEBUG, INFO, WARNING, ERROR")
    parser.add_argument("--log-path", type=Path, default=Path("vessel_frame.log"))
    return parser.parse_args(argv)


def _log_admin_status(
    task: asyncio.Task, stop_event: asyncio.Event, logger: logging.Logger
) -> None:
    """
    Log the outcome if the admin server exits unexpectedly.

    Logs a warning when the task stops cleanly but unexpectedly and logs an
    exception on crash.
    """
    if task.cancelled():
        # Manual shutdown - nothing to report
        return
    
    try:
        task.result()
        logger.warning("Admin server stopped unexpectedly but cleanly")
    except Exception:
        logger.exception(
            "Admin server crashed - admin panel unavailable but data processing continues"
        )


def _init_logger(level: str, log_path: Path):
    """
    Configure root logging with console and optional rotating file output.

    Sets a formatter, clears existing handlers, and attaches a stream handler.
    If a log path is provided, also attaches a rotating file handler.

    Args:
        level (str): Log level name (e.g., "DEBUG", "INFO", "WARNING", "ERROR").
        log_path (Path): Path to the log file. If falsy, file logging is skipped.
    """
    logger: logging.Logger = logging.getLogger()

    logger.handlers.clear()
    logger.setLevel(level.upper())

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    if log_path:
        try:
            file_handler = RotatingFileHandler(
                log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception:
            logging.getLogger(__name__).exception("Failed to set up file logging")


async def _init_plugins(
    config_manager: ConfigManager,
    plugin_manager: PluginManager,
    bus: MessageBus,
    plugin_type: str,
    entry_point_group: str,
    logger: logging.Logger,
    data_dir: Path,
) -> list[Plugin]:
    """
    Instantiate and start plugins of a given type from configuration.

    Reads the configured plugin names, resolves each via the plugin manager,
    starts them and returns the list of running plugin instances.

    Args:
        config_manager (ConfigManager): Source of plugin configuration.
        plugin_manager (PluginManager): Used to create plugin instances from entry points.
        bus (MessageBus): Injected into each plugin's constructor kwargs.
        plugin_type (str): The category to load the plugin from " (e.g., "sources", "processors").
        entry_point_group (str): The Python entry point group to resolve.
        logger (logging.Logger): Logger for status and error messages.

    Returns:
        list[Plugin]: Successfully started plugin instances (may be empty).
    """

    plugins: list[Plugin] = []
    configured_plugins = config_manager.get(f"plugins.{plugin_type}", [])

    for plugin_name in configured_plugins:
        try:
            plugin_config = config_manager.get(plugin_name)
            kwargs = plugin_config if isinstance(plugin_config, dict) else {}
            kwargs["bus"] = bus
            kwargs["data_dir"] = data_dir

            plugin = plugin_manager.create(entry_point_group, plugin_name, **kwargs)
            await plugin.start()
            plugins.append(plugin)

            logger.info(f"Started plugin '{plugin_name}' ({plugin_type})")
        except Exception:
            logger.exception(f"Failed to start plugin '{plugin_name}' ({plugin_type})")

    return plugins


async def run(argv: list[str] | None = None) -> int:
    """Application entry coroutine: start services, load plugins and run until stopped.

    Args:
        argv (list[str] | None): Optional CLI arguments.

    Returns:
        int: Process exit code (0 on success, non-zero on startup failure).
    """
    args = _parse_args(argv)

    _init_logger(args.log_level, args.log_path)
    logger = logging.getLogger(__name__)

    # Setup stop event for graceful shutdown
    stop_event = asyncio.Event()
    config_manager = ConfigManager(args.config)
    bus = MessageBus()
    plugin_manager = PluginManager()
    vessel_repo = VesselRepository(args.db)
    vessel_manager = VesselManager(bus, vessel_repo, in_topic="ais.decoded")
    network_manager = NetworkManager()
    asset_manager = AssetManager(Path(__file__).parent / "assets")

    auth.init(args.data_dir)

    try:
        config_manager.load()
    except Exception:
        logger.exception(f"Failed to load config from {args.config}")
        return 1

    admin_task = asyncio.create_task(start_admin_server(config_manager, plugin_manager, network_manager, host="0.0.0.0"))
    admin_task.add_done_callback(
        partial(_log_admin_status, stop_event=stop_event, logger=logger)
    )

    # Track all plugins for cleanup
    sources: list[Plugin] = []
    processors: list[Plugin] = []

    await vessel_repo.start()
    await vessel_manager.start()

    sources = await _init_plugins(
        config_manager, plugin_manager, bus, "sources", GROUP_SOURCES, logger, args.data_dir
    )
    processors = await _init_plugins(
        config_manager, plugin_manager, bus, "processors", GROUP_PROCESSORS, logger, args.data_dir
    )
    controllers = await _init_plugins(
        config_manager, plugin_manager, bus, "controllers", GROUP_CONTROLLERS, logger, args.data_dir
    )

    if not sources:
        logger.warning("No sources started")

    # Set up the renderer
    screen_manager: ScreenManager | None = None
    configured_renderers = config_manager.get("plugins.renderer", None)
    if configured_renderers is not None:
        # configured_renderers is an array to conform to the same patterns as other plugins
        # but only one renderer can be active, so we take the first one from the list.
        configured_renderer = configured_renderers[0]
        renderer_config = config_manager.get(configured_renderer)
        kwargs = renderer_config if isinstance(renderer_config, dict) else {}
        kwargs["data_dir"] = args.data_dir
        renderer: RendererPlugin = plugin_manager.create(
            GROUP_RENDERER, configured_renderer, **kwargs
        )

        screen_manager = ScreenManager(bus, plugin_manager, renderer, vessel_manager, cm=config_manager, asset_manager=asset_manager, data_dir=args.data_dir)
        await screen_manager.start()
    else:
        logger.warning("No renderer created")

    logger.info("System running. Press Ctrl+C to stop.")

    try:
        if sys.platform != "win32":
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop_event.set)

        await stop_event.wait()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        logger.info("Shutting down...")
        await vessel_repo.stop()
        await vessel_manager.stop()

        # Stop the admin server
        logger.info("Stopping admin server...")
        if not admin_task.done():
            admin_task.cancel()
            with suppress(asyncio.CancelledError):
                await admin_task

        # Cleanup all plugins
        logger.info("Stopping plugins...")
        for source in sources:
            try:
                await source.stop()
            except Exception:
                logger.exception("Error stopping source")

        for processor in processors:
            try:
                await processor.stop()
            except Exception:
                logger.exception("Error stopping processor")

        for controller in controllers:
            try:
                await controller.stop()
            except Exception:
                logger.exception("Error stopping controller")

        if screen_manager is not None:
            await screen_manager.stop()
        await bus.shutdown()

        logger.info("Shutdown complete.")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(run(argv))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
