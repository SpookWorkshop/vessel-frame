#!/bin/bash
set -e  # Exit on error

# Colours for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Colour

echo -e "${GREEN}=== Vessel Frame Setup ===${NC}"
echo ""

# Check we're in the right directory
if [ ! -f "scripts/setup.sh" ]; then
    echo -e "${RED}Error: This script must be run from the vessel-frame directory${NC}"
    echo "Please run: cd vessel-frame && bash scripts/setup.sh"
    exit 1
fi

# Check we're not running as root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}Error: Do not run this script with sudo${NC}"
    echo "The script will ask for sudo when needed"
    exit 1
fi

# Check if running on a Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo -e "${YELLOW}Warning: Cannot detect device model${NC}"
    echo "This script is designed for Raspberry Pi hardware"
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled"
        exit 0
    fi
elif ! grep -q "Raspberry Pi" /proc/device-tree/model; then
    echo -e "${YELLOW}Warning: This does not appear to be a Raspberry Pi${NC}"
    echo "Detected: $(cat /proc/device-tree/model)"
    echo "This script is designed for Raspberry Pi hardware"
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled"
        exit 0
    fi
fi

# Check OS version
if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [[ "$VERSION_CODENAME" != "trixie" ]]; then
        echo -e "${YELLOW}Warning: Unsupported OS version detected${NC}"
        echo "Expected: Debian Trixie"
        echo "Detected: $PRETTY_NAME (codename: $VERSION_CODENAME)"
        echo "The installation may not work correctly"
        read -p "Continue anyway? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Setup cancelled"
            exit 0
        fi
    fi
else
    echo -e "${YELLOW}Warning: Cannot detect OS version${NC}"
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled"
        exit 0
    fi
fi

echo -e "${YELLOW}This script will set up Vessel Frame on your Raspberry Pi${NC}"
echo "It will:"
echo "  - Install system dependencies"
echo "  - Enable I2C and SPI"
echo "  - Set up a Python virtual environment"
echo "  - Install core and plugins"
echo "  - Configure systemd services"
echo ""
read -p "Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Setup cancelled"
    exit 0
fi

echo ""
echo -e "${GREEN}Step 1: Installing system dependencies${NC}"
sudo apt update
sudo apt install -y python3.13-dev dnsmasq hostapd

echo -e "${GREEN}System dependencies installed${NC}"

echo ""
echo -e "${GREEN}Step 2: Enabling I2C and SPI${NC}"

# Enable I2C and SPI using raspi-config (0 = enabled)
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0

echo -e "${GREEN}I2C and SPI enabled${NC}"

# Add SPI overlay to boot config if not already present
echo -e "${GREEN}Step 3: Configuring boot settings${NC}"

if ! grep -q "dtoverlay=spi0-0cs" /boot/firmware/config.txt; then
    echo "dtoverlay=spi0-0cs" | sudo tee -a /boot/firmware/config.txt > /dev/null
    echo -e "${GREEN}Added SPI overlay to boot config${NC}"
else
    echo -e "${YELLOW}SPI overlay already present in boot config${NC}"
fi

echo ""
echo -e "${GREEN}Step 4: Updating repository${NC}"

# Check if there are uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo -e "${YELLOW}Warning: You have uncommitted changes in the repository${NC}"
    read -p "Skip git pull? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        echo -e "${YELLOW}Skipping git pull${NC}"
    else
        git pull
        echo -e "${GREEN}Repository updated${NC}"
    fi
else
    git pull
    echo -e "${GREEN}Repository updated${NC}"
fi

echo ""
echo -e "${GREEN}Step 5: Setting up Python virtual environment${NC}"

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    python3 -m venv .venv --system-site-packages
    echo -e "${GREEN}Virtual environment created${NC}"
else
    echo -e "${YELLOW}Virtual environment already exists${NC}"
fi

# Activate venv
source .venv/bin/activate

echo -e "${GREEN}Virtual environment activated${NC}"

echo ""
echo -e "${GREEN}Step 6: Installing core and plugins${NC}"

# Always install core and AIS decoder
echo "Installing vf_core and AIS decoder..."
pip install ./core
pip install ./plugins/message_processors/ais_decoder_processor
echo -e "${GREEN}Core and AIS decoder installed${NC}"

# Ask about hardware
echo ""
echo -e "${YELLOW}Hardware Configuration${NC}"

# AIS receiver
echo ""
read -p "Are you using a Wegmatt Daisy Mini AIS receiver? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    pip install ./plugins/message_sources/daisy_message_source
    echo -e "${GREEN}Daisy message source installed${NC}"
else
    echo -e "${YELLOW}Skipped - you'll need to install a message source for your AIS receiver${NC}"
fi

# Display
echo ""
read -p "Are you using a Pimoroni Inky display? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    pip install ./plugins/renderers/inky_renderer
    echo -e "${GREEN}Inky renderer installed${NC}"
else
    echo -e "${YELLOW}Skipped - you'll need to install a renderer for your display${NC}"
fi

# Ask about screen plugins
echo ""
echo -e "${YELLOW}Screen Plugins${NC}"
echo "Available screen types:"
echo ""

SCREEN_COUNT=0

read -p "Install Table Screen plugin? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    pip install ./plugins/screens/table_screen
    echo -e "${GREEN}Table Screen installed${NC}"
    SCREEN_COUNT=$((SCREEN_COUNT + 1))
fi

read -p "Install Zone Screen plugin? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    pip install ./plugins/screens/zone_screen
    echo -e "${GREEN}Zone Screen installed${NC}"
    SCREEN_COUNT=$((SCREEN_COUNT + 1))
fi

# Ask about button controller
echo ""
read -p "Install Button Controller? (recommended if your device has physical buttons) [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    pip install ./plugins/controllers/button_controller
    echo -e "${GREEN}Button Controller installed${NC}"
    if [ $SCREEN_COUNT -le 1 ]; then
        echo -e "${YELLOW}Note: Button controller is most useful with multiple screens${NC}"
    fi
else
    if [ $SCREEN_COUNT -gt 1 ]; then
        echo -e "${YELLOW}Note: You have multiple screens but no navigation controller${NC}"
    fi
fi

echo ""
echo -e "${GREEN}Step 7: Creating configuration directory${NC}"

if [ ! -d "/etc/vessel-frame" ]; then
    sudo mkdir -p /etc/vessel-frame
    sudo chown $USER:$USER /etc/vessel-frame
    echo -e "${GREEN}Configuration directory created${NC}"
else
    echo -e "${YELLOW}Configuration directory already exists${NC}"
    # Make sure ownership is correct anyway
    sudo chown $USER:$USER /etc/vessel-frame
fi

echo ""
echo -e "${GREEN}Step 8: Setting up systemd services${NC}"

# Get the current username and home directory
USERNAME=$USER
HOME_DIR=$HOME

# Create the main vessel-frame service
echo "Creating vessel-frame.service..."
sudo tee /etc/systemd/system/vessel-frame.service > /dev/null <<EOF
[Unit]
Description=Vessel Frame
After=network.target

[Service]
Type=simple
User=$USERNAME
WorkingDirectory=$HOME_DIR/vessel-frame
ExecStart=$HOME_DIR/vessel-frame/.venv/bin/vf
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable vessel-frame.service
echo -e "${GREEN}vessel-frame.service created and enabled${NC}"

# Network mode service
echo ""
echo "Setting up network mode service..."

# Copy the network mode script
sudo cp ./scripts/network_mode_service.py /usr/local/bin/vessel-frame-network-mode-service
sudo chmod +x /usr/local/bin/vessel-frame-network-mode-service

# Create the network mode service
sudo tee /etc/systemd/system/vessel-frame-network-mode.service > /dev/null <<EOF
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
EOF

sudo systemctl daemon-reload
sudo systemctl enable vessel-frame-network-mode.service
echo -e "${GREEN}vessel-frame-network-mode.service created and enabled${NC}"

# Set up sudoers permissions
echo "Configuring sudo permissions for network management..."
sudo tee /etc/sudoers.d/vessel-frame > /dev/null <<EOF
$USERNAME ALL=(ALL) NOPASSWD: /usr/sbin/ip
$USERNAME ALL=(ALL) NOPASSWD: /usr/sbin/iwlist
$USERNAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart hostapd
$USERNAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop hostapd
$USERNAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl start hostapd
$USERNAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart dnsmasq
$USERNAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop dnsmasq
$USERNAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl start dnsmasq
$USERNAME ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart dhcpcd
EOF

# Set correct permissions on sudoers file
sudo chmod 0440 /etc/sudoers.d/vessel-frame

echo -e "${GREEN}Sudo permissions configured${NC}"

echo ""
echo -e "${GREEN}Step 9: Configuring hostapd and dhcpcd${NC}"

# Configure hostapd
echo "Configuring hostapd..."
if grep -q "^DAEMON_CONF=" /etc/default/hostapd; then
    # Case 1: Line exists and is already uncommented
    sudo sed -i 's|^DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd
else
    # Case 2: Line doesn't exist OR is commented
    sudo sed -i 's|^#DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd
fi

echo -e "${GREEN}hostapd configured${NC}"

# Configure dhcpcd
echo "Configuring dhcpcd..."
if ! grep -q "denyinterfaces wlan0" /etc/dhcpcd.conf; then
    echo "" | sudo tee -a /etc/dhcpcd.conf > /dev/null
    echo "# Allow manual management of wlan0 for AP/Client switching" | sudo tee -a /etc/dhcpcd.conf > /dev/null
    echo "# denyinterfaces wlan0" | sudo tee -a /etc/dhcpcd.conf > /dev/null
    echo -e "${GREEN}dhcpcd configured${NC}"
else
    echo -e "${YELLOW}dhcpcd already configured${NC}"
fi

echo ""
echo -e "${GREEN}=== Setup Complete! ===${NC}"
echo ""
echo "Vessel Frame has been installed and configured."
echo "The system needs to reboot to apply all changes."
echo ""
echo "After reboot:"
echo "  1. The vessel-frame service will start automatically"
echo "  2. Access the admin panel at http://$(hostname -I | awk '{print $1}'):8000"
echo "  3. Enable your installed plugins through the admin panel"
echo "  4. The display should update once vessels are in range"
echo ""
read -p "Reboot now? [Y/n] " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "Rebooting..."
    sudo reboot
else
    echo ""
    echo -e "${YELLOW}Reboot postponed${NC}"
    echo "Remember to reboot before running Vessel Frame:"
    echo "  sudo reboot"
fi