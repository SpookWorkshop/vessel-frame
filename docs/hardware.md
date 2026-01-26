# Hardware

Vessel Frame uses a plugin architecture so you can mix and match components to suit your needs. This page covers tested hardware combinations and helps you identify which plugins you'll need.

## Tested Configuration

This is the hardware combination used during development and is fully supported:

| Component | Model | Plugin Required |
|-----------|-------|-----------------|
| Computer | Raspberry Pi Zero 2W | - |
| Operating System | Raspberry Pi OS Trixie | - |
| AIS Receiver | Wegmatt dAISy Mini | `daisy_message_source` |
| Display | Pimoroni Inky Impression | `inky_impression_renderer` |

## Hardware to Plugin Reference

### AIS Receivers

| Device | Connection | Plugin | Notes |
|--------|------------|--------|-------|
| Wegmatt dAISy Mini/FeatherWing | I2C | `daisy_message_source` | Compact, mounts directly to Pi header |
| Serial AIS receivers | USB | `serial_message_source` | Any receiver outputting NMEA sentences |

### Displays

| Display | Plugin | Notes |
|---------|--------|-------|
| Pimoroni Inky Impression Spectra 6 | `inky_renderer` | Latest Inky model with 6 colours, ~15 second refresh time |
| Pimoroni Inky Impression ACeP | `inky_renderer` | Gallery eInk model with 7 colours, ~40 second refresh time |

### Interaction

| Input Type | Source | Plugin | Notes |
|------------|--------|--------|-------|
| Button | Inky Impression | `button_controller` | |
| Button | GPIO | `button_controller` | Up to 4 buttons supported. Uses GPIO 5, 6, 16 and 24 |

### Raspberry Pi Models

Vessel Frame should run on any Raspberry Pi capable of running Pi OS Trixie, though performance will vary:

| Model | Status | Notes |
|-------|--------|-------|
| Pi Zero 2W | Supported | |
| Pi 3B+ | Untested | |
| Pi 4 | Untested | |
| Pi 5 | Untested | |

## Choosing Your Hardware

### Minimal Setup

For a basic vessel tracking display:

- Raspberry Pi Zero 2W
- Wegmatt dAISy Mini
- Pimoroni Inky Impression
- VHF Antenna

### Using Different Hardware

The plugin system means you're not limited to the tested configuration. If your hardware isn't listed:

1. Check if an existing plugin supports it
2. Look for community plugins in the [plugin list](plugin-list.md)
3. Create your own plugin — see [Creating Plugins](create-plugin.md)

## Hardware Tips

### AIS Receiver Antenna

The dAISy receivers require a VHF antenna tuned for marine AIS frequencies (161.975 MHz and 162.025 MHz). Reception quality depends heavily on:

- **Antenna quality**: A proper marine VHF antenna significantly outperforms the small whip antennas sometimes bundled with receivers
- **Antenna placement**: Near a window is preferable
- **Connections**: Ensure antenna connections are secure. Loose connections can cause unreliable reception

### E-ink Display Considerations

E-ink displays have a slow refresh rate (several seconds for a full update). Vessel Frame is designed around this limitation:

- Screen updates are batched and throttled
- The display won't show real-time movement, but provides a clear snapshot of vessel activity