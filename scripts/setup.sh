#!/bin/bash
set -e  # Exit on error

# Colours for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Colour

section() { echo ""; echo -e "${GREEN}$1${NC}"; }
note()    { echo -e "${YELLOW}$1${NC}"; }

echo -e "${GREEN}=== Vessel Frame Setup ===${NC}"
echo ""

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

# Must be run from the repo root
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

confirm_unsupported() {
    read -p "Continue anyway? [y/N] " -n 1 -r; echo
    [[ $REPLY =~ ^[Yy]$ ]] || { echo "Setup cancelled"; exit 0; }
}

# Raspberry Pi check
if [ ! -f /proc/device-tree/model ]; then
    note "Warning: cannot detect device model. This script targets Raspberry Pi hardware."
    confirm_unsupported
elif ! grep -q "Raspberry Pi" /proc/device-tree/model; then
    note "Warning: this does not appear to be a Raspberry Pi (detected: $(tr -d '\0' < /proc/device-tree/model))."
    confirm_unsupported
fi

# Check OS version
if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [[ "$VERSION_CODENAME" != "trixie" ]]; then
        note "Warning: expected Debian Trixie, detected $PRETTY_NAME (codename: $VERSION_CODENAME)."
        confirm_unsupported
    fi
else
    note "Warning: cannot detect OS version."
    confirm_unsupported
fi

# whiptail drives the menus. It ships with Raspberry Pi OS but install as a safety net
if ! command -v whiptail >/dev/null 2>&1; then
    note "Installing whiptail (needed for the setup menus)..."
    sudo apt update && sudo apt install -y whiptail
fi

# ---------------------------------------------------------------------------
# Collect all choices up front
# ---------------------------------------------------------------------------

cancelled() { echo "Setup cancelled"; exit 0; }

AIS_SOURCE=$(whiptail --title "AIS Source" --radiolist \
    "Choose your AIS data source:" 12 74 2 \
    rtlsdr "RTL-SDR dongle via AIS-catcher" ON \
    skip   "I'll configure my own source later"    OFF \
    3>&1 1>&2 2>&3) || cancelled

RENDERER=$(whiptail --title "Display Renderer" --radiolist \
    "Choose your display renderer:" 12 74 3 \
    inky  "Pimoroni Inky e-ink display"            ON \
    image "PNG image output (no display hardware)" OFF \
    skip  "I'll configure my own renderer later"   OFF \
    3>&1 1>&2 2>&3) || cancelled

# --separate-output makes the checklist print one tag per line (no quoting)
SCREENS=$(whiptail --title "Screens" --separate-output --checklist \
    "Select screens to install (SPACE toggles, ENTER confirms):" 12 74 3 \
    table "Vessel table"                ON \
    zone  "Zone proximity (needs a Mapbox key)"      OFF \
    map   "Map view (needs a Mapbox key)" OFF \
    3>&1 1>&2 2>&3) || cancelled

if whiptail --title "Button Controller" --yesno \
    "Install the button controller for physical navigation buttons?" 8 74; then
    INSTALL_BUTTON=yes
else
    INSTALL_BUTTON=no
fi

if whiptail --title "Network Service" --yesno \
    "Install the WiFi AP/client network-mode service?\n\nRecommended for headless setups so you can switch the device between hotspot and home-WiFi modes." 11 74; then
    INSTALL_NETWORK=yes
else
    INSTALL_NETWORK=no
fi

# Summary + single confirmation
SCREEN_LIST=$(echo $SCREENS | tr '\n' ' ')
[ -z "$SCREEN_LIST" ] && SCREEN_LIST="(none)"
whiptail --title "Confirm" --yesno \
"About to install Vessel Frame with:

  AIS source:  $AIS_SOURCE
  Renderer:    $RENDERER
  Screens:     $SCREEN_LIST
  Button:      $INSTALL_BUTTON
  Network svc: $INSTALL_NETWORK

This will install system packages, set up a virtualenv, and configure
systemd services. Proceed?" 18 74 || cancelled

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

section "Step 1: Installing system dependencies"
APT_PKGS="python3-dev git curl"
[ "$INSTALL_NETWORK" = yes ] && APT_PKGS="$APT_PKGS dnsmasq hostapd"
sudo apt update
sudo apt install -y $APT_PKGS

# I2C/SPI are only needed for the Inky display
if [ "$RENDERER" = inky ]; then
    section "Step 2: Enabling I2C and SPI for the Inky display"
    sudo raspi-config nonint do_i2c 0
    sudo raspi-config nonint do_spi 0
    if ! grep -q "dtoverlay=spi0-0cs" /boot/firmware/config.txt; then
        echo "dtoverlay=spi0-0cs" | sudo tee -a /boot/firmware/config.txt > /dev/null
        echo -e "${GREEN}Added SPI overlay to boot config${NC}"
    else
        note "SPI overlay already present in boot config"
    fi
fi

# RTL-SDR + AIS-catcher
if [ "$AIS_SOURCE" = rtlsdr ]; then
    section "Step 3: Installing AIS-catcher (RTL-SDR decoder)"
    # Official installer: pulls SDR libraries, builds AIS-catcher, and sets up
    # the ais-catcher.service systemd unit.
    curl -fsSL https://raw.githubusercontent.com/jvde-github/AIS-catcher/main/scripts/aiscatcher-install -o /tmp/aiscatcher-install
    sudo bash /tmp/aiscatcher-install -p
    rm -f /tmp/aiscatcher-install

    # Stop the kernel DVB-T driver from claiming the RTL-SDR dongle.
    echo "blacklist dvb_usb_rtl28xxu" | sudo tee /etc/modprobe.d/blacklist-rtl-sdr.conf > /dev/null

    # Point AIS-catcher's output at our UDP source on localhost.
    sudo mkdir -p /etc/AIS-catcher
    echo "-u 127.0.0.1 10110" | sudo tee /etc/AIS-catcher/config.cmd > /dev/null

    sudo systemctl enable ais-catcher.service
    sudo systemctl restart ais-catcher.service
    echo -e "${GREEN}AIS-catcher installed and feeding udp://127.0.0.1:10110${NC}"
else
    note "Skipping AIS source install. Install and configure one before running Vessel Frame."
fi

section "Step 4: Updating repository"
if git diff-index --quiet HEAD -- 2>/dev/null; then
    git pull && echo -e "${GREEN}Repository updated${NC}"
else
    note "Uncommitted changes present, skipping git pull"
fi

section "Step 5: Setting up Python virtual environment"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv --system-site-packages
    echo -e "${GREEN}Virtual environment created${NC}"
else
    note "Virtual environment already exists"
fi
source .venv/bin/activate

section "Step 6: Installing core and plugins"
pip install ./core
pip install ./plugins/message_processors/ais_decoder_processor

if [ "$AIS_SOURCE" = rtlsdr ]; then
    pip install ./plugins/message_sources/udp_message_source
fi

if [ "$RENDERER" = inky ]; then
    pip install ./plugins/renderers/inky_renderer
elif [ "$RENDERER" = image ]; then
    pip install ./plugins/renderers/image_renderer
else
    note "Skipping renderer install. Install and configure one before running Vessel Frame."
fi

for screen in $SCREENS; do
    screen_dir="./plugins/screens/${screen}_screen"
    if [ -d "$screen_dir" ]; then
        pip install "$screen_dir"
        echo -e "${GREEN}Installed ${screen}_screen${NC}"
    else
        echo -e "${RED}Warning: $screen_dir not found, skipping${NC}"
    fi
done

if [ "$INSTALL_BUTTON" = yes ]; then
    pip install ./plugins/controllers/button_controller
    echo -e "${GREEN}Button controller installed${NC}"
fi
echo -e "${GREEN}Core and plugins installed${NC}"

section "Step 7: Creating data and config directories"
# NetworkManager writes here. Core needs it writable even without the network service.
sudo mkdir -p /etc/vessel-frame
sudo chown "$USER:$USER" /etc/vessel-frame
sudo mkdir -p /var/lib/vessel-frame
sudo chown "$USER:$USER" /var/lib/vessel-frame
sudo chmod 700 /var/lib/vessel-frame
echo -e "${GREEN}Directories ready${NC}"

section "Step 8: Setting up the Vessel Frame service"
sudo tee /etc/systemd/system/vessel-frame.service > /dev/null <<EOF
[Unit]
Description=Vessel Frame
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/vessel-frame
ExecStart=$HOME/vessel-frame/.venv/bin/vf
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable vessel-frame.service
echo -e "${GREEN}vessel-frame.service enabled${NC}"

# Network mode service (optional)
if [ "$INSTALL_NETWORK" = yes ]; then
    section "Step 9: Setting up the network-mode service"
    sudo cp ./scripts/network_mode_service.py /usr/local/bin/vessel-frame-network-mode-service
    sudo chmod +x /usr/local/bin/vessel-frame-network-mode-service

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

    sudo tee /etc/sudoers.d/vessel-frame > /dev/null <<EOF
$USER ALL=(ALL) NOPASSWD: /usr/sbin/ip
$USER ALL=(ALL) NOPASSWD: /usr/sbin/iwlist
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart hostapd
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop hostapd
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start hostapd
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart dnsmasq
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop dnsmasq
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start dnsmasq
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart dhcpcd
EOF
    sudo chmod 0440 /etc/sudoers.d/vessel-frame

    # hostapd: point the daemon at our config path
    if grep -q "^DAEMON_CONF=" /etc/default/hostapd; then
        sudo sed -i 's|^DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd
    else
        sudo sed -i 's|^#DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd
    fi

    # dhcpcd: leave a commented hint our network script manages at runtime
    if ! grep -q "denyinterfaces wlan0" /etc/dhcpcd.conf; then
        {
            echo ""
            echo "# Allow manual management of wlan0 for AP/Client switching"
            echo "# denyinterfaces wlan0"
        } | sudo tee -a /etc/dhcpcd.conf > /dev/null
    fi
    echo -e "${GREEN}Network-mode service configured${NC}"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

section "=== Setup Complete! ==="
echo ""
echo "Vessel Frame is installed. A reboot is needed to apply all changes."
echo ""
echo "After reboot:"
echo "  1. The vessel-frame service starts automatically."
echo "  2. Open the admin panel at http://$(hostname -I | awk '{print $1}'):8000"
echo "  3. Enable your installed plugins there (and set zone/Mapbox details if you"
echo "     installed the zone or map screens)."
echo "  4. The display updates once vessels are in range."
echo ""
read -p "Reboot now? [Y/n] " -n 1 -r; echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "Rebooting..."
    sudo reboot
else
    note "Reboot postponed, reboot before starting Vessel Frame."
fi
