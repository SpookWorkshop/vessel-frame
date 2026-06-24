# Vessel Frame
A desktop picture frame that can receive AIS messages from nearby ships and display the information

## Features
- Real-time ship AIS tracking
- 3 visualisations: Zone, Table and Map
- Extensible plugin architecture so new visualisations can be added (or extend the whole thing for ADSB etc)
- Admin panel for configuring and managing plugins

## Get Started
### Hardware Compatibility
The project is designed to work with the following hardware setup:
 - Raspberry Pi Zero 2W or 3A+
 - Raspberry Pi OS Headless Trixie
 - RTL-SDR V3
 - [Pimoroni Inky Impression](https://shop.pimoroni.com/products/inky-impression-7-3?variant=55186435244411)

Other hardware may be supported. See the [hardware](./docs/hardware.md) or [plugins](./docs/plugin-list.md) page for a full list

### Configure the Raspberry Pi
Use Raspberry Pi Imager to set up your SD card.

When selecting the Operating System, choose "Raspberry Pi OS (other)" then "Raspberry Pi OS (32/64-bit) Lite".

When the imager asks if you want to set up configuration options, choose yes and set up both SSH and WiFi.

### Set up the OS environment
SSH into the Pi so you can set it up.

First install the required dependencies:
```bash
sudo apt update
sudo apt install git
```

Next check out the project onto the Pi:
First check out the project from the repository and move into the project directory
```bash
git clone https://github.com/SpookWorkshop/vessel-frame.git vessel-frame
cd vessel-frame
```

Make sure the setup script is executable, then execute it. It will start by asking a series of questions about your setup then install the required plugins. At the end of the setup the device will reboot and automatically run the vessel-frame project.
```bash
chmod +x scripts/setup.sh
bash scripts/setup.sh
```

### Enable Plugins
In a browser on any other device, navigate to http://[YOUR_PI_IP_ADDR]:8000. You should see the admin panel.
The first time you visit the admin panel you will need to set up a username and password. This will be used to log in on subsequent visits. There can be only one user account for the admin panel.

Once you've logged in you will see a list of installed plugins. Enable each one in turn and expand the row to set any required config parameters. Once all plugins are enabled, save and restart the program or the Pi for the changes to take effect.