#!/usr/bin/env python3
# Local imports
from bt import BT_Interface
from config import Session_Config
from i2c import I2C_Interface

import time


def _resolve_device_address(bt: BT_Interface, scanned_devices: dict[str, str], device_name: str) -> str | None:
    for addr, name in scanned_devices.items():
        if name == device_name:
            return str(addr)

    for addr, name in bt.devices(audio_sink=True).items():
        if name == device_name:
            return str(addr)

    return None


def _handle_output_device_actions(
    i2c: I2C_Interface,
    bt: BT_Interface,
    logger,
    scanned_devices: dict[str, str],
) -> bool:
    handled = False

    disconnect_name = i2c.take_audio_out_disconnect_name().strip()
    if disconnect_name:
        handled = True
        address = _resolve_device_address(bt, scanned_devices, disconnect_name)
        if address is None:
            logger.warning(f"Disconnect requested for '{disconnect_name}', but no matching MAC was found")
        else:
            logger.info(f"Disconnect requested for '{disconnect_name}' at {address}")
            bt.disconnect(address)

    forget_name = i2c.take_audio_out_forget_name().strip()
    if forget_name:
        handled = True
        address = _resolve_device_address(bt, scanned_devices, forget_name)
        if address is None:
            logger.warning(f"Forget requested for '{forget_name}', but no matching MAC was found")
        else:
            logger.info(f"Forget requested for '{forget_name}' at {address}")
            bt.disconnect(address)
            bt.untrust(address)
            bt.unpair(address)

    return handled


def _announce_output_devices(i2c: I2C_Interface, devices: dict[str, str], repeats: int = 3) -> None:
    for _ in range(repeats):
        for device_name in devices.values():
            i2c.write_audio_out_name(device_name)
            print(f"Found device: {device_name}")
            time.sleep(0.3)


def _connect_selected_output(
    bt: BT_Interface,
    logger,
    scanned_devices: dict[str, str],
    device_name: str,
) -> None:
    address = _resolve_device_address(bt, scanned_devices, device_name)
    if address is None:
        raise ValueError(f"No address found for device {device_name}")

    print(f"Attempting to connect to {device_name}, with address {address}")
    logger.info(f"Attempting to connect to '{device_name}' at {address}")

    bt.pair(address)
    bt.trust(address)
    bt.connect(address)

    print(f"Connected to {device_name} with address {address}")
    logger.info(f"Connected to '{device_name}' at {address}")


def main() -> int:
    cfg = Session_Config()
    bt = BT_Interface(cfg.logger)
    i2c = I2C_Interface(autostart=True, enable_voice_test=False, emit_logs=True)

    print(i2c.get_state())

    assert bt.power_off()
    assert bt.power_on()
    assert bt.agent_on()

    scanned_devices: dict[str, str] = {}
    last_selected_name = ""

    try:
        while True:
            if _handle_output_device_actions(i2c, bt, cfg.logger, scanned_devices):
                last_selected_name = ""

            scanned_devices = bt.scan(duration=15)
            _announce_output_devices(i2c, scanned_devices)
            if _handle_output_device_actions(i2c, bt, cfg.logger, scanned_devices):
                last_selected_name = ""
                continue

            selected_name = i2c.get_audio_out_name().strip()
            if not selected_name or selected_name == last_selected_name:
                time.sleep(0.5)
                continue

            _connect_selected_output(bt, cfg.logger, scanned_devices, selected_name)
            last_selected_name = selected_name

            while True:
                if _handle_output_device_actions(i2c, bt, cfg.logger, scanned_devices):
                    last_selected_name = ""
                    break
                current_selected_name = i2c.get_audio_out_name().strip()
                if current_selected_name != last_selected_name:
                    break
                time.sleep(0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        i2c.stop()


if __name__ == "__main__":
    raise SystemExit(main())
