# Plugin List

Vessel Frame's functionality is provided almost entirely through plugins. This page lists all known plugins, both built in and community contributed.

**Don't see a plugin you need?** [Create your own](create-plugin.md) and submit a PR to add it to this list.

### Message Sources
| Plugin Name | Created By | Link | Description |
|-------------|------------|------|-------------|
| com_message_source | Spook | Built In | For reading AIS data over USB |
| daisy_message_source | Spook | Built In | For reading AIS data over I2C from a dAISy Mini/FeatherWing |
| mock_message_source | Spook | Built In | For testing without a real receiver or in low traffic volume areas. Pre-recorded real AIS strings are output at randomised intervals in a loop. IMPORTANT: Ensure this data is never used for testing connections with a real tracking service |

### Message Processors
| Plugin Name | Created By | Link | Description |
|-------------|------------|------|-------------|
| ais_decoder_processor | Spook | Built In | Decoder for all AIS message types which outputs the data in a dictionary |

### Screens
| Plugin Name | Created By | Link | Description |
|-------------|------------|------|-------------|
| zone_screen | Spook | Built In | Displays information about a single vessel as it enters a predefined geofence |
| table_screen | Spook | Built In | Displays a table showing the vessels that have been heard from over the past 5 minutes |

### Renderers
| Plugin Name | Created By | Link | Description |
|-------------|------------|------|-------------|
| inky_renderer | Spook | Built In | Renderer for displaying screens on any Inky device (note: presently only tested on 7-inch ACeP and Spectra displays) |
| image_renderer | Spook | Built In | Renderer which writes the display to a png on the filesystem. Useful for testing screen layouts in different dimensions |

### Controllers
| Plugin Name | Created By | Link | Description |
|-------------|------------|------|-------------|
| button_controller | Spook | Built In | A controller supporting four GPIO-connected buttons that can be used for switching between screens. Also works with the 4 built in buttons on Inky devices which include them |


## Adding Your Plugin

To add your plugin to this list:

1. Ensure it follows the plugin structure outlined in [Creating Plugins](create-plugin.md)
2. Submit a pull request adding a row to the appropriate table above
3. Include: plugin name, your name/handle, repository link and a brief description