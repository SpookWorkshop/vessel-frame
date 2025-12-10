import subprocess
import json
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import asyncio


@dataclass
class NetworkConfig:
    """Network config data structure"""

    mode: str = "client"  # "ap" or "client"
    ap_ssid: str = "vessel-frame"
    ap_password: str = "spook_workshop"
    ap_channel: int = 6
    ap_ip: str = "10.0.0.1"
    client_ssid: Optional[str] = None
    client_password: Optional[str] = None
    auto_fallback: bool = True
    fallback_timeout: int = 60

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "NetworkConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


class NetworkManager:
    CONFIG_FILE = Path("/etc/vessel-frame/network_config.json")
    INTERFACE = "wlan0"

    # System paths for network configuration
    HOSTAPD_CONF = "/etc/hostapd/hostapd.conf"
    DNSMASQ_CONF = "/etc/dnsmasq.d/vessel-frame.conf"
    DHCPCD_CONF = "/etc/dhcpcd.conf"
    WPA_SUPPLICANT_CONF = "/etc/wpa_supplicant/wpa_supplicant.conf"

    def __init__(self, config_file: Optional[Path] = None):
        self._logger = logging.getLogger(__name__)

        if config_file:
            self.CONFIG_FILE = config_file

        self.config = self._load_config()
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        """Ensure configuration directory exists"""
        self.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> NetworkConfig:
        """Load configuration from file or create default"""

        try:
            if self.CONFIG_FILE.exists():
                with open(self.CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    return NetworkConfig.from_dict(data)
        except Exception as e:
            self._logger.error(f"Error loading network config: {e}")

        return NetworkConfig()

    def save_config(self):
        """Save current configuration to file"""

        try:
            self._ensure_config_dir()
            with open(self.CONFIG_FILE, "w") as f:
                json.dump(self.config.to_dict(), f, indent=2)
            self._logger.info("Network configuration saved")
        except Exception as e:
            self._logger.error(f"Error saving config: {e}")
            raise

    def get_current_mode(self) -> str:
        """Detect current network mode by checking running services

        Returns:
            str: 'ap', 'client' or 'unknown'
        """
        try:
            # Check if hostapd is running
            result = subprocess.run(
                ["systemctl", "is-active", "hostapd"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.stdout.strip() == "active":
                return "ap"

            # Check if connected as client
            result = subprocess.run(
                ["iwgetid", "-r"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return "client"
            
            return "unknown"
        except Exception as e:
            self._logger.error(f"Error detecting network mode: {e}")
            return "unknown"

    async def scan_networks_async(self) -> List[Dict[str, any]]:
        """Scan for available networks asynchronously

        Returns:
            List of dicts containing network info
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.scan_networks)

    def scan_networks(self) -> List[Dict[str, any]]:
        """Scan for available networks

        Returns:
            List of dicts containing network info
        """
        try:
            # Ensure interface is up for scanning
            subprocess.run(
                ["sudo", "ip", "link", "set", self.INTERFACE, "up"],
                capture_output=True,
                timeout=5,
            )

            # Wait for interface to be ready
            time.sleep(1)

            # Scan for networks
            result = subprocess.run(
                ["sudo", "iwlist", self.INTERFACE, "scan"],
                capture_output=True,
                text=True,
                timeout=15,
            )

            networks = []
            current_network = {}

            for line in result.stdout.split("\n"):
                line = line.strip()

                if "Cell " in line and "Address:" in line:
                    # Save previous network if exists
                    if current_network.get("ssid"):
                        networks.append(current_network.copy())
                    current_network = {}

                elif "ESSID:" in line:
                    ssid = line.split("ESSID:")[1].strip('"')
                    if ssid:
                        current_network["ssid"] = ssid

                elif "Quality=" in line:
                    try:
                        quality = line.split("Quality=")[1].split()[0]
                        current_network["quality"] = quality

                        if "Signal level=" in line:
                            signal = line.split("Signal level=")[1].split()[0]
                            current_network["signal"] = signal
                    except:
                        pass

                elif "Encryption key:" in line:
                    encrypted = "on" in line.lower()
                    current_network["encrypted"] = encrypted

            # Don't forget the last network
            if current_network.get("ssid"):
                networks.append(current_network.copy())

            # Remove duplicates and sort by signal strength
            seen = set()
            unique_networks = []
            for net in networks:
                if net["ssid"] not in seen:
                    seen.add(net["ssid"])
                    unique_networks.append(net)

            self._logger.info(f"Found {len(unique_networks)} networks")
            return unique_networks

        except subprocess.TimeoutExpired:
            self._logger.error("Network scan timed out")
            return []
        except Exception as e:
            self._logger.error(f"Error scanning networks: {e}")
            return []

    def schedule_mode_change(self, new_mode: str, **kwargs) -> Tuple[bool, str]:
        """Schedule a mode change for next boot

        This updates the config file but doesn't immediately apply changes.
        The changes will take effect when the system is rebooted or when
        apply_config() is called.

        Args:
            new_mode: The mode to switch to ('ap' or 'client')
            **kwargs: Additional configuration parameters

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            self.config.mode = new_mode

            # Update any provided configuration
            for key, value in kwargs.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)

            self.save_config()

            return (
                True,
                f"Network mode changed to '{new_mode}'. Changes will apply after reboot.",
            )

        except Exception as e:
            self._logger.error(f"Error scheduling mode change: {e}")
            return False, str(e)

    def get_status(self) -> Dict[str, any]:
        """Get current network status

        Returns:
            Dictionary containing current status information
        """
        status = {
            "configured_mode": self.config.mode,
            "actual_mode": self.get_current_mode(),
            "timestamp": datetime.now().isoformat(),
            "config_file": str(self.CONFIG_FILE),
        }

        actual_mode = status["actual_mode"]

        if actual_mode == "ap":
            status["ap_ssid"] = self.config.ap_ssid
            status["ap_ip"] = self.config.ap_ip

        elif actual_mode == "client":
            try:
                result = subprocess.run(
                    ["iwgetid", "-r"], capture_output=True, text=True, timeout=5
                )
                status["connected_ssid"] = result.stdout.strip()

                result = subprocess.run(
                    ["hostname", "-I"], capture_output=True, text=True, timeout=5
                )
                ip_addresses = result.stdout.strip().split()
                status["ip_address"] = ip_addresses[0] if ip_addresses else None
            except:
                pass

        return status

    def get_config_dict(self) -> dict:
        """Get current configuration as a dictionary

        Passwords are masked for security.

        Returns:
            Dictionary of current configuration
        """
        config = self.config.to_dict()

        # Mask passwords
        if config.get("ap_password"):
            config["ap_password"] = "****"
            
        if config.get("client_password"):
            config["client_password"] = "****"

        return config

    def update_ap_config(
        self,
        ssid: Optional[str] = None,
        password: Optional[str] = None,
        channel: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Update AP mode configuration

        Args:
            ssid: New AP SSID
            password: New AP password
            channel: New wifi channel

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if ssid is not None:
                if not ssid.strip():
                    return False, "SSID cannot be empty"
                self.config.ap_ssid = ssid.strip()

            if password is not None:
                if len(password) < 8:
                    return False, "Password must be at least 8 characters"
                self.config.ap_password = password

            if channel is not None:
                if channel not in range(1, 12):
                    return False, "Channel must be between 1 and 11"
                self.config.ap_channel = channel

            self.save_config()
            return True, "AP configuration updated"

        except Exception as e:
            self._logger.error(f"Error updating AP config: {e}")
            return False, str(e)

    def update_client_config(
        self,
        ssid: str,
        password: str,
        auto_fallback: Optional[bool] = None,
        fallback_timeout: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Update client mode configuration

        Args:
            ssid: Network SSID to connect to
            password: Network password
            auto_fallback: Whether to fall back to AP mode on failure
            fallback_timeout: Seconds to wait before falling back

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if not ssid.strip():
                return False, "SSID cannot be empty"

            self.config.client_ssid = ssid.strip()
            self.config.client_password = password

            if auto_fallback is not None:
                self.config.auto_fallback = auto_fallback

            if fallback_timeout is not None:
                if fallback_timeout < 30 or fallback_timeout > 300:
                    return False, "Fallback timeout must be between 30 and 300 seconds"
                self.config.fallback_timeout = fallback_timeout

            self.save_config()
            return True, "Client configuration updated"

        except Exception as e:
            self._logger.error(f"Error updating client config: {e}")
            return False, str(e)
