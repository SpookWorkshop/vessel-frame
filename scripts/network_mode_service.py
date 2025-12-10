#!/usr/bin/env python3

"""
Vessel Frame Network Configuration

This script runs at boot via systemd to set up the
network according to the user's preferences.
"""

import time
import json
import subprocess
import logging
import sys
from pathlib import Path
from typing import Dict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/var/log/vessel-frame-network-mode.log')
    ]
)
logger = logging.getLogger('vf_network')

# Configuration paths
CONFIG_FILE = Path("/etc/vessel-frame/network_config.json")
HOSTAPD_CONF = "/etc/hostapd/hostapd.conf"
DNSMASQ_CONF = "/etc/dnsmasq.d/vessel-frame.conf"
WPA_SUPPLICANT_CONF = "/etc/wpa_supplicant/wpa_supplicant.conf"
INTERFACE = "wlan0"


def load_config() -> Dict:
    """Load network configuration from file"""

    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
    
    # Default to client mode
    return {"mode": "client"}


def configure_ap_mode(config: Dict) -> bool:
    """Configure the device as an access point"""

    logger.info(f"Configuring AP mode: {config.get('ap_ssid', 'vessel-frame')}")
    
    try:
        # Stop NetworkManager
        subprocess.run(['systemctl', 'stop', 'NetworkManager'], check=False)
        subprocess.run(['systemctl', 'stop', 'wpa_supplicant'], check=False)
        
        # Configure hostapd
        ap_ssid = config.get('ap_ssid', 'vessel-frame')
        ap_password = config.get('ap_password', 'spook_workshop')
        ap_channel = config.get('ap_channel', 6)
        
        hostapd_config = f"""interface={INTERFACE}
driver=nl80211
ssid={ap_ssid}
hw_mode=g
channel={ap_channel}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={ap_password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
"""
        
        with open(HOSTAPD_CONF, 'w') as f:
            f.write(hostapd_config)
        
        # Configure dnsmasq
        ap_ip = config.get('ap_ip', '10.0.0.1')
        dnsmasq_config = f"""interface={INTERFACE}
dhcp-range=10.0.0.2,10.0.0.20,255.255.255.0,24h
domain=wlan
address=/vessel-frame.local/{ap_ip}
address=/vessel-frame/{ap_ip}
"""
        
        with open(DNSMASQ_CONF, 'w') as f:
            f.write(dnsmasq_config)
        
        # Configure static IP
        subprocess.run(['ip', 'addr', 'flush', 'dev', INTERFACE], check=False)
        subprocess.run(['ip', 'addr', 'add', f'{ap_ip}/24', 'dev', INTERFACE], check=True)
        subprocess.run(['ip', 'link', 'set', INTERFACE, 'up'], check=True)
        
        # Start AP services
        subprocess.run(['systemctl', 'unmask', 'hostapd'], check=False)
        subprocess.run(['systemctl', 'restart', 'dnsmasq'], check=True)
        subprocess.run(['systemctl', 'restart', 'hostapd'], check=True)
        
        logger.info("AP mode configured successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error configuring AP mode: {e}", exc_info=True)
        return False


def configure_client_mode(config: Dict) -> bool:
    """Configure the device as a wifi client"""

    client_ssid = config.get('client_ssid')
    client_password = config.get('client_password', '')
    auto_fallback = config.get('auto_fallback', True)
    
    logger.info(f"Configuring client mode: {client_ssid}")
    
    if not client_ssid:
        logger.error("No client SSID configured")
        return False
    
    try:
        # Stop AP services and start NetworkManager
        subprocess.run(['systemctl', 'stop', 'hostapd'], check=False)
        subprocess.run(['systemctl', 'stop', 'dnsmasq'], check=False)
        
        # Remove static IP
        subprocess.run(['ip', 'addr', 'flush', 'dev', INTERFACE], check=False)
        
        # Start NetworkManager
        subprocess.run(['systemctl', 'start', 'NetworkManager'], check=True)
        
        # Create wpa_supplicant configuration for NetworkManager
        wpa_config = f"""ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=GB

network={{
    ssid="{client_ssid}"
    psk="{client_password}"
    key_mgmt=WPA-PSK
}}
"""
        
        with open(WPA_SUPPLICANT_CONF, 'w') as f:
            f.write(wpa_config)
        
        # Set permissions
        subprocess.run(['chmod', '600', WPA_SUPPLICANT_CONF], check=True)
        
        # Give NetworkManager time to connect
        timeout = config.get('fallback_timeout', 60)
        
        logger.info(f"Waiting up to {timeout}s for NetworkManager to connect...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            time.sleep(1)
            
            # Check if connected via NetworkManager
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'GENERAL.STATE', 'device', 'show', INTERFACE],
                capture_output=True,
                text=True
            )
            
            if 'connected' in result.stdout.lower():
                logger.info("Connected to network successfully")
                return True
        
        logger.warning(f"Failed to connect within {timeout}s")
        
        # Fall back to AP mode if configured
        if auto_fallback:
            logger.info("Fallback enabled, switching to AP mode")
            return configure_ap_mode(config)
        
        return False
        
    except Exception as e:
        logger.error(f"Error configuring client mode: {e}", exc_info=True)
        
        # Try fallback if enabled
        if auto_fallback:
            logger.info("Client network mode error, switching to AP mode")
            return configure_ap_mode(config)
        
        return False

def main():
    logger.info("Starting network mode config")
    
    config = load_config()
    mode = config.get('mode', 'client')
    
    logger.info(f"Network mode: {mode}")
    
    if mode == 'ap':
        success = configure_ap_mode(config)
    elif mode == 'client':
        success = configure_client_mode(config)
    else:
        logger.error(f"Unknown mode: {mode}")
        success = False
    
    if success:
        logger.info("Network config applied successfully")
        return 0
    else:
        logger.error("Failed to apply network config")
        return 1


if __name__ == "__main__":
    sys.exit(main())