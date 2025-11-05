import logging
from .message_bus import MessageBus
from .plugin_manager import PluginManager
from .plugin_types import GROUP_SCREENS, RendererPlugin, ScreenPlugin
from .vessel_manager import VesselManager

class ScreenManager:
    def __init__(self, bus: MessageBus, pm: PluginManager, renderer: RendererPlugin, vm: VesselManager) -> None:
        self._logger = logging.getLogger(__name__)
        self._bus = bus
        self._pm = pm
        self._screens: list[ScreenPlugin] = []
        self._renderer = renderer
        self._vm = vm
        self._active_screen: ScreenPlugin | None = None

    async def start(self) -> None:
        for entry_point in self._pm.iter_entry_points(GROUP_SCREENS):
            screen: ScreenPlugin = self._pm.create(GROUP_SCREENS, entry_point.name, bus=self._bus, renderer=self._renderer, vm=self._vm)
            self._screens.append(screen)
        
        if self._screens:
            self._active_screen = self._screens[0]
            await self._active_screen.activate()
        else:
            self._logger.warning("No screens loaded")

    async def stop(self) -> None:
        if self._active_screen:
            try:
                await self._active_screen.deactivate()
            except Exception:
                self._logger.exception("Error deactivating screen")