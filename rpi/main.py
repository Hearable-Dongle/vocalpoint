#!/usr/bin/env python3
# Local imports
from bt import BT_Interface
from config import Session_Config
from i2c import I2C_Interface

import time


def main() -> int:
    # Load session configuration
    cfg = Session_Config()

    # Create Bluetooth interface with logger
    bt = BT_Interface(cfg.logger)

    i2c = I2C_Interface(
        autostart=True,
        enable_voice_test=False,
    )
    print(i2c.get_state())

    # Initialize Bluetooth interface
    assert bt.power_off()
    assert bt.power_on()
    assert bt.agent_on()

    while(True):
        try:
            # Scan for devices and connect to configured sink
            devices = bt.scan(duration = 15) # 15 seconds was found to be the minimum time required

            write_device_count = 3

            for count in range(write_device_count):
                for device in devices.values():
                    i2c.write_audio_out_name(device)
                    print(f"Found device: {device}")
                    time.sleep(0.3)
                count += 1

            while i2c.get_audio_out_name() == "":
                time.sleep(0.3)

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

            while(True):
                time.sleep(1)

        except KeyboardInterrupt:
            return 0

    # assert cfg.sink in devices

    # Print Bluetooth sink information
    print(bt.info(cfg.sink))

# Script entry point
if __name__ == "__main__":
    raise SystemExit(main())