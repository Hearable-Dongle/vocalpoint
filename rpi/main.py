#!/usr/bin/env python3
import time

from bt import BT_Interface
from usb import USB_Interface
from config import Session_Config
from i2c import I2C_Interface
import numpy as np


def callback(audio_bytes: bytes, channels: int) -> bytes:
    """Callback that receives audio frame and sends to Bluetooth sink."""
    # Convert bytes to numpy array
    audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
    
    # Extract only the first channel from interleaved audio data
    # PyAudio delivers interleaved channels: [L0, R0, C0, LFE0, SL0, SR0, L1, R1, ...]
    # So we take every channels-th sample starting from index 0
    first_channel = audio_int16[::channels]  # Get samples 0, 6, 12, 18, ... (first channel)
    
    # Convert back to bytes
    output_bytes = first_channel.astype(np.int16).tobytes()
    
    return output_bytes


BLE_SCAN_SEC = 15
SCAN_INTERVAL_SEC = 5.0
CONNECT_RETRY_COOLDOWN_SEC = 1.0
IDLE_SLEEP_SEC = 0.2

def _normalize_device_name(name: str) -> str:
    return name.strip().casefold()

def _merge_devices_list(cache: dict[str, str], new_devices: dict[str, str]) -> None:
    for addr, name in new_devices.items():
        cache[str(addr)] = name

def _resolve_device_address(bt: BT_Interface, cached_devices: dict[str, str], device_name: str) -> str | None:
    wanted = _normalize_device_name(device_name)

    for addr, name in cached_devices.items():
        if _normalize_device_name(name) == wanted:
            return str(addr)

    for addr, name in bt.devices(audio_sink=True).items():
        addr_str = str(addr)
        cached_devices[addr_str] = name
        if _normalize_device_name(name) == wanted:
            return addr_str

    return None

def _handle_output_device_actions(i2c: I2C_Interface, bt: BT_Interface, logger, cached_devices: dict[str, str]) -> bool:
    handled = False
    disconnect_name = i2c.take_audio_out_disconnect_name().strip()

    if disconnect_name:
        handled = True
        address = _resolve_device_address(bt, cached_devices, disconnect_name)
        if address is None:
            print(f"Disconnect requested for {disconnect_name}, but no matching MAC was found")
            logger.warning(f"Disconnect requested for '{disconnect_name}', but no matching MAC was found")
        else:
            logger.info(f"Disconnect requested for '{disconnect_name}' at {address}")
            bt.disconnect(address)

    forget_name = i2c.take_audio_out_forget_name().strip()
    if forget_name:
        handled = True
        address = _resolve_device_address(bt, cached_devices, forget_name)
        if address is None:
            print(f"Forget requested for {forget_name}, but no matching MAC was found")
            logger.warning(f"Forget requested for '{forget_name}', but no matching MAC was found")
        else:
            logger.info(f"Forget requested for '{forget_name}' at {address}")
            bt.disconnect(address)
            bt.untrust(address)
            bt.unpair(address)
            cached_devices.pop(address, None)

    return handled

def _send_output_devices(i2c: I2C_Interface, devices: dict[str, str]) -> None:
    for device_name in devices.values():
        for count in range(3):
            i2c.write_audio_out_name(device_name)
            print(f"Found device: {device_name}")
            time.sleep(0.3)
            count += 1

def _scan_and_cache(bt: BT_Interface, cached_devices: dict[str, str], duration: int = BLE_SCAN_SEC) -> dict[str, str]:
    scanned_devices = bt.scan(duration=duration)
    _merge_devices_list(cached_devices, scanned_devices)
    return scanned_devices

def _connect_selected_output(bt: BT_Interface, logger, cached_devices: dict[str, str], device_name: str) -> bool:
    address = _resolve_device_address(bt, cached_devices, device_name)

    if address is None:
        print(f"No address found for selected device: {device_name}")
        logger.warning(f"No address found for selected device '{device_name}'")
        return False

    if not bt.pair(address):
        return False
    if not bt.trust(address):
        return False
    if not bt.connect(address):
        return False

    print(f"Connected to {device_name} with address {address}")
    logger.info(f"Connected to '{device_name}' at {address}")
    return True

def main() -> int:
    cfg = Session_Config()

    # Initialize Bluetooth, USB and I2C interfaces
    bt = BT_Interface(cfg.logger)
    usb = USB_Interface(cfg.logger, cfg.source, cfg.fs, cfg.frame)
    i2c = I2C_Interface(autostart=True, enable_voice_test=False, emit_logs=True)

    # Configure Bluetooth interface
    assert bt.power_off()
    assert bt.power_on()
    assert bt.agent_on()

    # Configure USB interface
    assert usb.connect()

    cached_devices: dict[str, str] = {}
    last_announced_at = 0.0
    last_selected_name = ''
    next_connect_attempt_at = 0.0

    try:
        while True:
            now = time.monotonic()

            if _handle_output_device_actions(i2c, bt, cfg.logger, cached_devices):
                last_selected_name = ''
                next_connect_attempt_at = now

            selected_name = i2c.get_audio_out_name().strip()

            if selected_name and selected_name != last_selected_name and now >= next_connect_attempt_at:
                print(f"Selected output from app: {selected_name}")

                if _connect_selected_output(bt, cfg.logger, cached_devices, selected_name):
                    last_selected_name = selected_name

                else:
                    _scan_and_cache(bt, cached_devices, duration=BLE_SCAN_SEC)

                    if _connect_selected_output(bt, cfg.logger, cached_devices, selected_name):
                        last_selected_name = selected_name

                    else:
                        next_connect_attempt_at = time.monotonic() + CONNECT_RETRY_COOLDOWN_SEC

            now = time.monotonic()
            should_scan_for_outputs = (not selected_name) or (not last_selected_name)
            if should_scan_for_outputs and now - last_announced_at >= SCAN_INTERVAL_SEC:
                _scan_and_cache(bt, cached_devices, duration=BLE_SCAN_SEC)

                if cached_devices:
                    _send_output_devices(i2c, cached_devices)

                last_announced_at = time.monotonic()

            time.sleep(IDLE_SLEEP_SEC)
    except KeyboardInterrupt:
        return 0
    finally:
        i2c.stop()


if __name__ == "__main__":
    raise SystemExit(main())
