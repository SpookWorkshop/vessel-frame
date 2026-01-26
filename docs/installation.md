# Installation

### Hardware Compatibility
This project has been tested with the following hardware setup:
 - Raspberry Pi Zero 2W
 - Raspberry Pi OS Headless Trixie
 - [Wegmatt Daisy Mini](https://shop.wegmatt.com/products/daisy-mini-ais-receiver)
 - [Pimoroni Inky Impression 7](https://shop.pimoroni.com/products/inky-impression-7-3?variant=55186435244411) (Gallery and Spectra 6 models both supported)

On the Daisy Mini, connect the 5V, GND, SDA and SCL pins to the same pins on the Inky screen's connector

### Configure the Raspberry Pi
Use Raspberry Pi Imager to set up your SD card.

When selecting the Operating System, choose "Raspberry Pi OS (other)" then "Raspberry Pi OS (32/64-bit) Lite".

When the imager asks if you want to set up configuration options, choose yes and set up both SSH and WiFi.

### Set up the OS enviroment
SSH into the Pi so you can set it up.

First install the required dependencies:
```bash
sudo apt update
sudo apt install git
```

Now decide whether you want to run the setup script to get started or go through the manual setup process. If you are using the officially supported hardware then the setup script is the best option.

## Set up via script

First check out the project from the repository and move into the project directory
```bash
git clone https://github.com/SpookWorkshop/vessel-frame.git vessel-frame
cd vessel-frame
```
Now make sure the setup script is executable
```bash
chmod +x scripts/setup.sh
```
Finally, run the script. It will ask questions during the process which you can answer with Y or N. At the end of the setup the device will reboot and then automatically run the vessel-frame project.
```bash
bash scripts/setup.sh
```


## Set up manually
If you need to customise the setup or have different hardware requirements that need 3rd party plugins, you should go through the manual setup process.

### Set up the OS enviroment
SSH into the Pi so you can set it up.

First install the rest of the required dependencies:
```bash
sudo apt install python3.13-dev dnsmasq hostapd
```

Next, enable I2C and SPI in raspi-config:
```bash
sudo raspi-config
```

Enable I2C and SPI:
```
To enable I2C:
Choose "Interface Options" > I2C > Enable.

To enable SPI:
Choose "Interface Options" > SPI > Enable.
```

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
python -m venv .venv --system-site-packages

# Activate venv (Linux)
source .venv/bin/activate
# Activate venv (Windows)
.venv\Scripts\activate
```

### Install vf_core & plugins
These are the default plugins. If you have different hardware requirements then you'll need other plugins to provide support, for example non-inky screens won't work with the inky_renderer and will need a renderer specific to that screen type.
```bash
pip install ./core
pip install ./plugins/message_sources/daisy_message_source
pip install ./plugins/message_processors/ais_decoder_processor
pip install ./plugins/renderers/inky_renderer
pip install ./plugins/screens/table_screen
pip install ./plugins/screens/zone_screen
pip install ./plugins/controllers/button_controller
```
Create a place for the network config to be stored
```bash
sudo mkdir -p /etc/vessel-frame
sudo chown $USER:$USER /etc/vessel-frame
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

### Setup wifi mode service
If you want to be able to switch between AP, Client and Disabled network modes you need to install the network management service.
First, move the network mode manager script into /usr/local/bin and make it executable:
```bash
sudo cp ./scripts/network_mode_service.py /usr/local/bin/vessel-frame-network-mode-service
sudo chmod +x /usr/local/bin/vessel-frame-network-mode-service
```

Now set up systemd to run this service on boot.
```bash
sudo nano /etc/systemd/system/vessel-frame-network-mode.service
```
Use the following template for the service file:
```
[Unit]
Description=Vessel Frame Network Boot Configuration
Before=vessel-frame.service
After=network-pre.target
Wants=network-pre.target

[Service]
Type=oneshot
User=root
ExecStart=/usr/local/bin/vessel-frame-network-mode-service
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```
Now enable the new network mode service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable vessel-frame-network-mode
```

In order to modify the network settings this script needs sudo access. Set up passwordless sudo with this command:
```bash
sudo visudo
```
At the bottom of the file, add the following lines (replacing [YOUR USERNAME] for your actual username)
```
[YOUR USERNAME] ALL=(ALL) NOPASSWD: /usr/sbin/ip
[YOUR USERNAME] ALL=(ALL) NOPASSWD: /usr/sbin/iwlist
[YOUR USERNAME] ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart hostapd
[YOUR USERNAME] ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop hostapd
[YOUR USERNAME] ALL=(ALL) NOPASSWD: /usr/bin/systemctl start hostapd
[YOUR USERNAME] ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart dnsmasq
[YOUR USERNAME] ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop dnsmasq
[YOUR USERNAME] ALL=(ALL) NOPASSWD: /usr/bin/systemctl start dnsmasq
[YOUR USERNAME] ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart dhcpcd
```


Now set up hostapd and dhcpcd.
```bash
sudo nano /etc/default/hostapd
```
You will see the line "DAEMON_CONF" but it is commented out (with the # at the start)
Replace that line with:
```
DAEMON_CONF="/etc/hostapd/hostapd.conf"
```
Now edit the dhcpcd config
```bash
sudo nano /etc/dhcpcd.conf
```
At the end of the file add the following. It is correct that this is commented out as our script will manage it later
```
# Allow manual management of wlan0 for AP/Client switching
# denyinterfaces wlan0
```
