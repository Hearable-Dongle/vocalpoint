#!/usr/bin/env python3

import time

from bt import BT_Interface
from config import Session_Config
from i2c import I2C_Interface
from wifi import WifiManager


def _normalized_wifi_request(i2c: I2C_Interface) -> tuple[str, str]:
    return (i2c.get_wifi_ssid().strip(), i2c.get_wifi_pwd().strip())


def _handle_wifi_updates(
    i2c: I2C_Interface,
    wifi: WifiManager,
    logger,
    last_wifi_request: tuple[str, str],
) -> tuple[str, str]:
    current_wifi_request = _normalized_wifi_request(i2c)
    if current_wifi_request == last_wifi_request:
        return last_wifi_request

    wifi_ssid, wifi_pwd = current_wifi_request
    print(
        f"[main] wifi request changed:"
        f" ssid='{wifi_ssid}' password_len={len(wifi_pwd)}"
    )
    logger.info(
        f"Wi-Fi request changed: ssid='{wifi_ssid}' password_len={len(wifi_pwd)}"
    )
    if wifi_ssid and wifi_pwd:
        result = wifi.connect_from_i2c(wifi_ssid, wifi_pwd)
        logger.info(result)
        print(result)
    else:
        print("[main] wifi request incomplete, waiting for both SSID and password")

    return current_wifi_request


def main() -> int:
    cfg = Session_Config()
    bt = BT_Interface(cfg.logger)
    wifi = WifiManager(cfg.logger, "wlan0")

    i2c = I2C_Interface(
        autostart=True,
        enable_voice_test=False,
    )
    print(f"[main] initial i2c state: {i2c.get_state()}")

    last_wifi_request = ("", "")

    assert bt.power_off()
    assert bt.power_on()
    assert bt.agent_on()

    while True:
        try:
            last_wifi_request = _handle_wifi_updates(
                i2c,
                wifi,
                cfg.logger,
                last_wifi_request,
            )

            devices = bt.scan(duration=15)

            write_device_count = 3
            for _ in range(write_device_count):
                for device in devices.values():
                    i2c.write_audio_out_name(device)
                    print(f"Found device: {device}")
                    time.sleep(0.3)
                    last_wifi_request = _handle_wifi_updates(
                        i2c,
                        wifi,
                        cfg.logger,
                        last_wifi_request,
                    )

            while i2c.get_audio_out_name() == "":
                time.sleep(0.3)
                last_wifi_request = _handle_wifi_updates(
                    i2c,
                    wifi,
                    cfg.logger,
                    last_wifi_request,
                )

            device_name = i2c.get_audio_out_name()
            print(f"Device name from app: {device_name}")

            address = next(
                (addr for addr, name in devices.items() if name == device_name),
                None,
            )

            if address is None:
                raise ValueError(f"No address found for device {device_name}")

            print(f"Attempting to connect to {device_name}, with address {address}")

            assert bt.pair(address)
            assert bt.trust(address)
            assert bt.connect(address)

            print(f"Connected to {device_name} with address {address}")

            while True:
                time.sleep(1)
                last_wifi_request = _handle_wifi_updates(
                    i2c,
                    wifi,
                    cfg.logger,
                    last_wifi_request,
                )

        except KeyboardInterrupt:
            i2c.stop()
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
