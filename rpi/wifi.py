import subprocess
import textwrap
import unicodedata
from typing import List


class WifiManager:
    _SSID_PUNCT_TRANSLATION = str.maketrans(
        {
            "\u2018": "'",
            "\u2019": "'",
            "\u201C": '"',
            "\u201D": '"',
            "\u2013": "-",
            "\u2014": "-",
            "\u00A0": " ",
        }
    )

    def __init__(self, logger, ifname: str = "wlan0") -> None:
        self.__logger = logger
        self.ifname = ifname
        self.__logger.info(f"WifiManager initialized for interface {self.ifname}")

    def __strip_text(self, text: str) -> str:
        return text.strip() if text else ""

    def __ssid_lookup_key(self, ssid: str) -> str:
        normalized = unicodedata.normalize("NFKC", self.__strip_text(ssid))
        normalized = normalized.translate(self._SSID_PUNCT_TRANSLATION)
        return normalized.casefold()

    def __resolve_scanned_ssid(
        self,
        requested_ssid: str,
        available_networks: List[str],
    ) -> str | None:
        requested_ssid = self.__strip_text(requested_ssid)
        if requested_ssid in available_networks:
            return requested_ssid

        requested_key = self.__ssid_lookup_key(requested_ssid)
        for network in available_networks:
            if self.__ssid_lookup_key(network) == requested_key:
                return network
        return None

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
        sudo_cmd = ["sudo", *cmd]
        return subprocess.run(sudo_cmd, check=check, text=True, capture_output=True)

    def scan_networks(self) -> List[str]:
        try:
            self.run(["nmcli", "radio", "wifi", "on"])
            self.__logger.info("Wi-Fi radio enabled")
            print(f"[wifi] radio enabled on {self.ifname}")
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
            print(f"[wifi] rescan requested on {self.ifname}")
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
        if networks:
            self.__logger.info(
                "Available Wi-Fi networks:\n" + textwrap.indent("\n".join(networks), "\t")
            )
            print("[wifi] available networks:")
            for network in networks:
                print(f"[wifi]   {network}")
        else:
            self.__logger.info("Available Wi-Fi networks: none found")
            print("[wifi] available networks: none found")
        return networks

    def connect_from_i2c(self, ssid: str, password: str) -> str:
        requested_ssid = ssid.strip()
        password = password

        self.__logger.info(f"Received Wi-Fi connect request for SSID '{requested_ssid}'")
        print(f"[wifi] received connect request for SSID '{requested_ssid}'")

        if not requested_ssid:
            self.__log_failure(
                "connect_from_i2c.validate_ssid",
                error="Missing SSID from I2C input",
            )
            return "Error: username/network name is wrong"

        if password == "":
            self.__log_failure(
                "connect_from_i2c.validate_password",
                ssid=requested_ssid,
                error="Missing password from I2C input",
            )
            return "Error: password is wrong"

        current = self.current_wifi()
        if current == requested_ssid:
            self.__logger.info(f"Already connected to Wi-Fi network '{requested_ssid}'")
            print(f"[wifi] already connected to '{requested_ssid}'")
            return f"Connected to {requested_ssid}"

        available_networks = self.scan_networks()
        target_ssid = self.__resolve_scanned_ssid(requested_ssid, available_networks)
        if not isinstance(target_ssid, str) or not target_ssid:
            print(
                f"[wifi] requested SSID '{requested_ssid}' was not found in scanned"
                " networks, attempting direct nmcli connect anyway"
            )
            self.__logger.info(
                f"SSID '{requested_ssid}' not found in scan results, attempting direct connect"
            )
            target_ssid = requested_ssid

        if target_ssid != requested_ssid:
            print(
                f"[wifi] matched requested SSID '{requested_ssid}'"
                f" to scanned SSID '{target_ssid}'"
            )
            self.__logger.info(
                f"Matched requested SSID '{requested_ssid}' to scanned SSID '{target_ssid}'"
            )

        print(f"[wifi] target SSID '{target_ssid}' found, attempting nmcli connect")
        result = self.run(
            [
                "nmcli",
                "device",
                "wifi",
                "connect",
                target_ssid,
                "password",
                password,
                "ifname",
                self.ifname,
            ],
            check=False,
        )
        print(f"[wifi] nmcli connect return code: {result.returncode}")
        if result.stdout.strip():
            print(f"[wifi] nmcli stdout: {result.stdout.strip()}")
        if result.stderr.strip():
            print(f"[wifi] nmcli stderr: {result.stderr.strip()}")

        if result.returncode != 0:
            self.__log_failure(
                "connect_from_i2c.connect",
                ssid=target_ssid,
                output=result.stdout,
                error=result.stderr,
            )
            combined_output = f"{result.stdout}\n{result.stderr}".lower()
            if "no network with ssid" in combined_output:
                return "Error: username/network name is wrong"
            if "password" in combined_output:
                return "Error: password is wrong"
            return "Error: failed to connect to network"

        self.__logger.info(f"Connected to Wi-Fi network '{target_ssid}' on {self.ifname}")
        print(f"[wifi] connected to '{target_ssid}' on {self.ifname}")
        current = self.current_wifi()
        print(f"[wifi] current active network after connect: '{current}'")
        return f"Connected to {target_ssid}"

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
