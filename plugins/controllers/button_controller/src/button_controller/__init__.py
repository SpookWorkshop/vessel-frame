from gpiozero import Button
import asyncio
import logging
from vf_core.plugin_types import Plugin, ConfigSchema, ConfigField, ConfigFieldType
from vf_core.message_bus import MessageBus

class ButtonController(Plugin):
    """Handles physical button presses."""
    
    def __init__(
        self,
        *,
        bus: MessageBus,
        button_a_pin: int = 5,
        button_b_pin: int = 6,
        button_c_pin: int = 16,
        button_d_pin: int = 24,
    ):
        self._logger = logging.getLogger(__name__)
        self._loop = None
        self._bus = bus
        
        try:
            # Set up GPIO buttons
            self._button_a = Button(button_a_pin, pull_up=True)
            self._button_b = Button(button_b_pin, pull_up=True)
            self._button_c = Button(button_c_pin, pull_up=True)
            self._button_d = Button(button_d_pin, pull_up=True)
            
            # Wire up button events
            self._button_a.when_pressed = self._on_button_a
            self._button_b.when_pressed = self._on_button_b
            self._button_c.when_pressed = self._on_button_c
            self._button_d.when_pressed = self._on_button_d

            self._logger.info("Button controller initialised")
        except Exception as e:
            self._logger.error(f"Failed to initialise buttons: {e}")
            raise
    
    async def start(self):
        self._loop = asyncio.get_running_loop()
        self._logger.info("Button controller ready")
    
    async def stop(self):
        """Clean up GPIO resources."""
        try:
            self._button_a.close()
            self._button_b.close()
            self._button_c.close()
            self._button_d.close()
            self._logger.info("Button controller stopped")
        except Exception as e:
            self._logger.error(f"Error closing buttons: {e}")

    def _schedule_publish(self, action: str):
        """Schedule a publish from GPIO thread to asyncio event loop."""
        if self._loop is None:
            self._logger.error("Event loop not available, button press ignored")
            return
        
        asyncio.run_coroutine_threadsafe(
            self._bus.publish("screen.command", {"action": action}),
            self._loop
        )
    
    def _on_button_a(self):
        """Button A: Go to previous screen."""
        self._schedule_publish("previous")
    
    def _on_button_b(self):
        """Button B: Go to next screen."""
        self._schedule_publish("next")
    
    def _on_button_c(self):
        """Button C: No action yet."""
        self._logger.info("Button C pressed (no action configured)")
    
    def _on_button_d(self):
        """Button D: No action yet."""
        self._logger.info("Button D pressed (no action configured)")


def get_config_schema() -> ConfigSchema:
    return ConfigSchema(
        plugin_name="button_controller",
        plugin_type="controller",
        fields=[
            ConfigField(
                key="button_a_pin",
                label="Button A GPIO Pin",
                field_type=ConfigFieldType.INTEGER,
                default=5,
                description="GPIO pin for button A (previous screen)"
            ),
            ConfigField(
                key="button_b_pin",
                label="Button B GPIO Pin",
                field_type=ConfigFieldType.INTEGER,
                default=6,
                description="GPIO pin for button B (next screen)"
            ),
            ConfigField(
                key="button_c_pin",
                label="Button C GPIO Pin",
                field_type=ConfigFieldType.INTEGER,
                default=16,
                description="GPIO pin for button C"
            ),
            ConfigField(
                key="button_d_pin",
                label="Button D GPIO Pin",
                field_type=ConfigFieldType.INTEGER,
                default=24,
                description="GPIO pin for button D"
            ),
        ]
    )

def make_plugin(**kwargs):
    return ButtonController(**kwargs)