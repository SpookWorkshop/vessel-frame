from .message_bus import MessageBus
from .plugin_manager import PluginManager
from .plugin_types import RendererPlugin, ScreenPlugin

class ScreenManager:
    def __init__(self, bus: MessageBus, pm: PluginManager, renderer: RendererPlugin) -> None:
        self._bus = bus
        self._pm = pm
        self._screens = []
        self._renderer = renderer

    async def start(self, screen_configs):
        for s in self._pm.iter_entry_points("vesselframe.plugins.screens"):
            print("Screen Entry Point " + s.name)
            screen:ScreenPlugin = self._pm.create("vesselframe.plugins.screens", s.name, bus=self._bus, renderer=self._renderer)
            self._screens.append(screen)
        
        if self._screens:
            self._active_screen = self._screens[0]

        await self._active_screen.activate()