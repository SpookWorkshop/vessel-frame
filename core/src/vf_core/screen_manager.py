from .message_bus import MessageBus
from .plugin_manager import PluginManager
from .plugin_types import RendererPlugin, ScreenPlugin
from .vessel_manager import VesselManager

class ScreenManager:
    def __init__(self, bus: MessageBus, pm: PluginManager, renderer: RendererPlugin, vm: VesselManager) -> None:
        self._bus = bus
        self._pm = pm
        self._screens = []
        self._renderer = renderer
        self._vm = vm

    async def start(self):
        for s in self._pm.iter_entry_points("vesselframe.plugins.screens"):
            screen:ScreenPlugin = self._pm.create("vesselframe.plugins.screens", s.name, bus=self._bus, renderer=self._renderer, vm=self._vm)
            self._screens.append(screen)
        
        if self._screens:
            self._active_screen = self._screens[0]
            await self._active_screen.activate()
        else:
            self._logger.warning("No screens loaded")

