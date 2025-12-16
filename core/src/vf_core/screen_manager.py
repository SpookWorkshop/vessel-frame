import asyncio
import logging

from vf_core.config_manager import ConfigManager
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
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._bus = bus
        self._pm = pm
        self._screens: list[ScreenPlugin] = []
        self._renderer = renderer
        self._vm = vm
        self._cm = cm
        self._asset_manager = asset_manager
        self._active_screen: ScreenPlugin | None = None
        self._current_screen_index: int = 0

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

        for screen_name in configured_screens:
            try:
                plugin_config = self._cm.get(screen_name)
                kwargs = plugin_config if isinstance(plugin_config, dict) else {}

                screen: ScreenPlugin = self._pm.create(
                    GROUP_SCREENS,
                    screen_name,
                    renderer=self._renderer,
                    vm=self._vm,
                    bus=self._bus,
                    asset_manager=self._asset_manager,
                    **kwargs
                )
                self._screens.append(screen)
                self._logger.info(f"Loaded screen: {screen_name}")
            except Exception:
                self._logger.exception(f"Failed to load screen '{screen_name}'")

        asyncio.create_task(self._loop())

        if self._screens:
            self._active_screen = self._screens[self._current_screen_index]
            await self._active_screen.activate()
        else:
            self._logger.warning("No screens loaded")

    async def stop(self) -> None:
        """Deactivate the screen manager and any active screen.

        Logs any exceptions raised during deactivation.
        """
        if self._active_screen:
            try:
                await self._active_screen.deactivate()
            except Exception:
                self._logger.exception("Error deactivating screen")

    async def _loop(self) -> None:
        """Listen for screen navigation commands."""
        async for message in self._bus.subscribe("screen.command"):
            action = message.get("action")
            
            if action == "next":
                await self._next_screen()
            elif action == "previous":
                await self._previous_screen()
    
    async def _next_screen(self):
        """Switch to next screen."""
        if not self._screens or len(self._screens) <= 1:
            return
        
        next_index = (self._current_screen_index + 1) % len(self._screens)
        await self._switch_to_screen(next_index)
    
    async def _previous_screen(self):
        """Switch to previous screen."""
        if not self._screens or len(self._screens) <= 1:
            return
        
        next_index = (self._current_screen_index - 1) % len(self._screens)
        await self._switch_to_screen(next_index)

    async def _switch_to_screen(self, target_index: int):
        """Switch to a specific screen"""
        
        self._logger.info(
            f"Switching from screen {self._current_screen_index} to {target_index}"
        )
        
        # Change the active screen
        await self._screens[self._current_screen_index].deactivate()
        self._current_screen_index = target_index
        await self._screens[self._current_screen_index].activate()