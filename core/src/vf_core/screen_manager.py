import asyncio
import logging
from contextlib import suppress

from pathlib import Path

from vf_core.config_manager import ConfigManager
from .error_screen import ErrorScreen
from .message_bus import MessageBus
from .plugin_manager import PluginManager
from .plugin_types import GROUP_SCREENS, RendererPlugin, ScreenPlugin
from .vessel_manager import VesselManager
from .asset_manager import AssetManager


class ScreenManager:
    def __init__(
        self,
        bus: MessageBus,
        pm: PluginManager,
        renderer: RendererPlugin,
        vm: VesselManager,
        cm: ConfigManager,
        asset_manager: AssetManager,
        data_dir: Path,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._bus = bus
        self._pm = pm
        self._screens: list[ScreenPlugin] = []
        self._renderer = renderer
        self._vm = vm
        self._cm = cm
        self._asset_manager = asset_manager
        self._data_dir = data_dir
        self._active_screen: ScreenPlugin | None = None
        self._error_screen = ErrorScreen(renderer, asset_manager)
        self._in_error = False
        self._error_recoverable = False
        self._previous_screen: ScreenPlugin | None = None
        self._command_task: asyncio.Task | None = None
        self._error_task: asyncio.Task | None = None
        self._cleared_task: asyncio.Task | None = None

    async def start(self) -> None:
        """
        Load and activate available screen plugins.

        Discovers all screen entry points from the plugin manager, creates
        instances, and activates the first one as the active screen. Logs a
        warning if no screens are found.
        """
        configured_screens = self._cm.get("plugins.screens", [])

        if not configured_screens:
            self._logger.warning("No screens configured in plugins.screens")
            return

        system_config = self._cm.get("SYSTEM") or {}

        for screen_name in configured_screens:
            try:
                plugin_config = self._cm.get(screen_name)
                kwargs = plugin_config if isinstance(plugin_config, dict) else {}

                # Inject system-level values that screens might need
                if "mapbox_api_key" not in kwargs:
                    kwargs["mapbox_api_key"] = system_config.get("mapbox_api_key", "")

                screen: ScreenPlugin = self._pm.create(
                    GROUP_SCREENS,
                    screen_name,
                    renderer=self._renderer,
                    vm=self._vm,
                    bus=self._bus,
                    asset_manager=self._asset_manager,
                    data_dir=self._data_dir,
                    **kwargs
                )
                self._screens.append(screen)
                self._logger.info(f"Loaded screen: {screen_name}")
            except Exception:
                self._logger.exception(f"Failed to load screen '{screen_name}'")

        self._command_task = asyncio.create_task(self._command_loop())
        self._error_task = asyncio.create_task(self._error_loop())
        self._cleared_task = asyncio.create_task(self._cleared_loop())

        if self._screens:
            self._active_screen = self._screens[0]
            await self._active_screen.activate()
        else:
            self._logger.warning("No screens loaded")

    async def stop(self) -> None:
        """Stop both loop tasks and deactivate the active screen."""
        for task in (self._command_task, self._error_task, self._cleared_task):
            if task and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        if self._active_screen:
            try:
                await self._active_screen.deactivate()
            except Exception:
                self._logger.exception("Error deactivating screen")

    async def _command_loop(self) -> None:
        """Listen for screen navigation commands."""
        async for message in self._bus.subscribe("screen.command"):
            if self._in_error:
                continue

            action = message.get("action")

            if action == "next":
                await self._next_screen()
            elif action == "previous":
                await self._previous_screen()

    async def _error_loop(self) -> None:
        """Listen for system error events and switch to the error screen."""
        async for message in self._bus.subscribe(MessageBus.TOPIC_SYSTEM_ERROR):
            await self._handle_error(message)

    async def _cleared_loop(self) -> None:
        """Listen for error-cleared events and restore the previous screen."""
        async for _ in self._bus.subscribe(MessageBus.TOPIC_SYSTEM_ERROR_CLEARED):
            await self._handle_cleared()

    async def _handle_error(self, message: dict) -> None:
        """Deactivate the current screen and show the error screen."""
        error_msg = message.get("message", "An unknown error occurred.")
        recovery = message.get("recovery", "")
        recoverable = bool(message.get("recoverable", False))

        self._logger.error(f"System error: {error_msg}")

        if self._active_screen and self._active_screen is not self._error_screen:
            self._previous_screen = self._active_screen
            try:
                await self._active_screen.deactivate()
            except Exception:
                self._logger.exception("Error deactivating screen before showing error")

        self._error_screen.set_error(error_msg, recovery)
        self._in_error = True
        self._error_recoverable = recoverable
        self._active_screen = self._error_screen

        try:
            await self._error_screen.activate()
        except Exception:
            self._logger.exception("Failed to render error screen")

    async def _handle_cleared(self) -> None:
        """Restore the previous screen after a recoverable error is resolved."""
        if not self._in_error:
            return

        if not self._error_recoverable:
            self._logger.warning("Received error_cleared for a non-recoverable error")
            return

        self._in_error = False
        self._error_recoverable = False

        screen = self._previous_screen or (self._screens[0] if self._screens else None)
        self._previous_screen = None

        if screen is None:
            self._logger.warning("No screen to restore after error cleared")
            return

        self._active_screen = screen
        try:
            await screen.activate()
        except Exception:
            self._logger.exception("Failed to restore screen after error cleared")

    async def _next_screen(self) -> None:
        """Switch to next screen."""
        if not self._screens or len(self._screens) <= 1 or self._active_screen is None:
            return

        current_index = self._screens.index(self._active_screen)
        await self._switch_to_screen((current_index + 1) % len(self._screens))

    async def _previous_screen(self) -> None:
        """Switch to previous screen."""
        if not self._screens or len(self._screens) <= 1 or self._active_screen is None:
            return

        current_index = self._screens.index(self._active_screen)
        await self._switch_to_screen((current_index - 1) % len(self._screens))

    async def _switch_to_screen(self, target_index: int) -> None:
        """Switch to a specific screen."""
        self._logger.info(
            f"Switching from '{type(self._active_screen).__name__ if self._active_screen else 'None'}' to '{type(self._screens[target_index]).__name__}'"
        )

        if self._active_screen:
            try:
                await self._active_screen.deactivate()
            except Exception:
                self._logger.exception("Error deactivating screen during switch")
        self._active_screen = self._screens[target_index]
        await self._active_screen.activate()
