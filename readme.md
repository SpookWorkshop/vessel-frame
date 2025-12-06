# Vessel Frame
A desktop picture frame that can receive AIS messages from nearby ships and display the information

## Features
- Real-time ship AIS tracking
- Multiple data visualisations
- Extensible plugin architecture
- Web admin panel

## Get Started
### Hardware Compatibility
This project has been tested with the following hardware setup:
 - Raspberry Pi Zero 2W
 - Raspberry Pi OS Headless Bookworm or Trixie
 - [Wegmatt Daisy Mini](https://shop.wegmatt.com/products/daisy-mini-ais-receiver)
 - [Pimoroni Inky Impression 7](https://shop.pimoroni.com/products/inky-impression-7-3?variant=55186435244411) (Gallery and Spectra 6 models both supported)


### Configure the Raspberry Pi
Use Raspberry Pi Imager to set up your SD card.

When selecting the Operating System, choose "Raspberry Pi OS (other)" then "Raspberry Pi OS (Legacy 32/64-bit) Lite".

When the imager asks if you want to set up configuration options, choose yes and set up both SSH and WiFi.

### Set up the OS enviroment
SSH into the Pi so you can set it up.

First install the required dependencies:
```bash
sudo apt update
sudo apt install git

#if using Trixie
sudo apt install python3.13-dev
#if using Bookworm
sudo apt install python3.11-dev
```

Next, enable I2C and SPI in raspi-config:
```bash
sudo raspi-config
```
To enable I2C: Choose "Interface Options" > I2C > Enable.
To enable SPI: Choose "Interface Options" > SPI > Enable.

Next edit the boot config:
```bash
sudo nano /boot/firmware/config.txt
```
At the end of the file, under "[all]", add "dtoverlay=spi0-0cs".

Now reboot the Pi and SSH back in.

### Check out the project
```bash
git clone https://github.com/SpookWorkshop/vessel-frame.git vessel-frame
cd vessel-frame
```

### Set up a virtual environment
The project must run in a python virtual environment
```bash
# Create the virtual env
python -m venv .venv

# Activate venv (Linux)
source .venv/bin/activate
# Activate venv (Windows)
.venv\Scripts\activate
```

### Install vf_core & plugins
```bash
pip install ./core
pip install ./plugins/message_sources/daisy_message_source
pip install ./plugins/message_processors/ais_decoder_processor
pip install ./plugins/renderers/inky_renderer
pip install ./plugins/screens/table_screen
```

### Run the project
```bash
vf
```
You should see some log output similar to the following:
```
[INFO] vf_core.web_admin.auth: Generated new JWT secret key
INFO:     Started server process [1114]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
[WARNING] vf_core.main: No sources started
[WARNING] vf_core.main: No renderer created
[INFO] vf_core.main: System running. Press Ctrl+C to stop.
```

### Enable Plugins
In a browser on any other device, navigate to http://[YOUR_PI_IP_ADDR]:8000. You should see the admin panel.
The first time you visit the admin panel you will need to set up a username and password. This will be used to log in on subsequent visits. There can be only one user account for the admin panel.

Once you've logged in you will see a list of installed plugins. Enable each one in turn. As you enable them you'll see an alert that you may need to restart. Wait until all plugins are enabled and then restart the program.

Once the code starts running you will see more log output indicating which plugins were loaded. If vessels are in range, the screen should update with the vessel table after around 30 seconds.

### Setup systemd service
In order for the code to run automatically if the device restarts, set up a systemd service
```bash
sudo nano /etc/systemd/system/vessel-frame.service
```
Use the following template for the systemd file, replacing [YOUR USERNAME] with your username
```
[Unit]
Description=Vessel Frame
After=network.target

[Service]
Type=simple
User=[YOUR USERNAME]
WorkingDirectory=/home/[YOUR USERNAME]/vessel-frame
ExecStart=/home/[YOUR USERNAME]/vessel-frame/.venv/bin/vf
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```
Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable vessel-frame
sudo systemctl start vessel-frame
```