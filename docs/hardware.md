# Hardware

Vessel Frame uses a plugin architecture so you can mix and match components to suit your needs. This page covers tested hardware combinations and helps you identify which plugins you'll need.

## Tested Configurations

This is the hardware combination used during development and is fully supported.

| Component | Model | Plugin Required |
|-----------|-------|-----------------|
| Computer | Raspberry Pi Zero 2W | - |
| Operating System | Raspberry Pi OS Trixie | - |
| AIS Receiver | RTL SDR v3 | `udp_message_source` |
| Display | Pimoroni Inky Impression | `inky_renderer` |

For other hardware configurations, refer to the lists below to see what is already supported and which plugins are required

## Hardware/Plugin Reference

### AIS Receivers

| Device | Connection | Plugin | Notes |
|--------|------------|--------|-------|
| RTL-SDR v3 | UDP | `udp_message_source` | Common, inexpensive software defined radio. Requires setting up software like AISCatcher to tune the radio and forward the raw data over UDP |
| Wegmatt dAISy Mini/FeatherWing | I2C/UART | `daisy_message_source` | Compact AIS receiver that outputs over ISC or UART |
| Serial AIS receivers | USB | `serial_message_source` | Any receiver outputting raw NMEA sentences |

### Displays

| Display | Plugin | Notes |
|---------|--------|-------|
| Pimoroni Inky Impression | `inky_renderer` | Tested with the previous 3 generations of Inky Impression: AC Waveform, Spectra 6 and ACeP/Gallery |

### Interaction

| Input Type | Source | Plugin | Notes |
|------------|--------|--------|-------|
| Button | Inky Impression | `button_controller` | |
| Button | GPIO | `button_controller` | Up to 4 buttons supported. Uses GPIO 5, 6, 16 and 24 by default but can be remapped |

### Raspberry Pi Models

Vessel Frame should run on any Raspberry Pi capable of running Pi OS Trixie, though performance will vary:

| Model | Status | Notes |
|-------|--------|-------|
| Pi Zero 2W | Supported | |
| Pi 3B+ | Supported | |
| Pi 4 | Untested | |
| Pi 5 | Untested | |

## Hardware Tips

### AIS Receiver Antenna

The receivers require a VHF antenna tuned for marine AIS frequencies (161.975 MHz and 162.025 MHz). Reception quality depends heavily on:

- **Antenna quality**: A proper marine VHF antenna significantly outperforms the small whip antennas sometimes bundled with receivers
- **Antenna placement**: Near a window is preferable, AIS signals are weak and easily blocked by walls
- **Connections**: Ensure antenna connections are secure. Loose connections can cause unreliable reception

### E-ink Display Considerations

E-ink displays have a slow refresh rate (several seconds for a full update). Vessel Frame is designed around this limitation:

- Screen updates are batched and throttled
- The display won't show real-time movement but provides a clear snapshot of vessel activity