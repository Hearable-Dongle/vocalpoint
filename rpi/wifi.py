import subprocess
import textwrap
from typing import List


class WifiManager:
    def __init__(self, logger, ifname: str = "wlan0") -> None:
        self.__logger = logger
        self.ifname = ifname
        self.__logger.info(f"WifiManager initialized for interface {self.ifname}")

    def __strip_text(self, text: str) -> str:
        return text.strip() if text else ""

    def __log_failure(
        self,
        operation: str,
        ssid: str = "",
        output: str = "",
        error: str = "",
    ) -> None:
        log_entry = f"\nOperation: {operation}"
        if ssid:
            log_entry += f"\nSSID: {ssid}"
        if output:
            log_entry += "\nOutput:\n" + textwrap.indent(self.__strip_text(output), "\t")
        if error:
            log_entry += "\nError:\n" + textwrap.indent(self.__strip_text(error), "\t")
        self.__logger.error(log_entry)

    def run(
        self,
        cmd: list[str],
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(cmd, check=check, text=True, capture_output=True)

    def scan_networks(self) -> List[str]:
        try:
            self.run(["nmcli", "radio", "wifi", "on"])
            self.__logger.info("Wi-Fi radio enabled")
        except subprocess.CalledProcessError as e:
            self.__log_failure(
                "scan_networks.radio_on",
                output=e.stdout,
                error=e.stderr,
            )
            return []

        result = self.run(
            ["nmcli", "device", "wifi", "rescan", "ifname", self.ifname],
            check=False,
        )
        if result.returncode == 0:
            self.__logger.info(f"Wi-Fi rescan requested on {self.ifname}")
        else:
            self.__log_failure(
                "scan_networks.rescan",
                output=result.stdout,
                error=result.stderr,
            )

        try:
            result = self.run(
                ["nmcli", "-t", "-f", "SSID", "device", "wifi", "list", "ifname", self.ifname]
            )
        except subprocess.CalledProcessError as e:
            self.__log_failure(
                "scan_networks.list",
                output=e.stdout,
                error=e.stderr,
            )
            return []

        networks: List[str] = []
        for line in result.stdout.splitlines():
            ssid = line.strip()
            if ssid and ssid not in networks:
                networks.append(ssid)

        self.__logger.info(f"Scanned {len(networks)} Wi-Fi networks on {self.ifname}")
        return networks

    def connect_from_i2c(self, ssid: str, password: str) -> str:
        ssid = ssid.strip()
        password = password.strip()

        self.__logger.info(f"Received Wi-Fi connect request for SSID '{ssid}'")

        if not ssid:
            self.__log_failure(
                "connect_from_i2c.validate_ssid",
                error="Missing SSID from I2C input",
            )
            return "Error: username/network name is wrong"

        available_networks = self.scan_networks()

        if ssid not in available_networks:
            self.__log_failure(
                "connect_from_i2c.network_lookup",
                ssid=ssid,
                error="Requested SSID not found in scanned networks",
            )
            return "Error: username/network name is wrong"

        result = self.run(
            [
                "nmcli",
                "device",
                "wifi",
                "connect",
                ssid,
                "password",
                password,
                "ifname",
                self.ifname,
            ],
            check=False,
        )

        if result.returncode != 0:
            self.__log_failure(
                "connect_from_i2c.connect",
                ssid=ssid,
                output=result.stdout,
                error=result.stderr,
            )
            return "Error: password is wrong"

        self.__logger.info(f"Connected to Wi-Fi network '{ssid}' on {self.ifname}")
        return f"Connected to {ssid}"

    def current_wifi(self) -> str:
        try:
            result = self.run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"])
        except subprocess.CalledProcessError as e:
            self.__log_failure(
                "current_wifi",
                output=e.stdout,
                error=e.stderr,
            )
            return ""

        for line in result.stdout.splitlines():
            if line.startswith("yes:"):
                ssid = line.split(":", 1)[1]
                self.__logger.info(f"Current Wi-Fi network is '{ssid}'")
                return ssid

        self.__logger.info("No active Wi-Fi network found")
        return ""


#EX
# from wifi_manager import WifiManager
# from config import Config

# cfg = Config()
# wifi = WifiManager(cfg.logger, "wlan0")

# print(wifi.scan_networks())
# print(wifi.connect_from_i2c("MyWifi", "mypassword"))
# print(wifi.current_wifi())
