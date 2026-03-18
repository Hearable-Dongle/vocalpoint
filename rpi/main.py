#!/usr/bin/env python3
# Local imports
from bt import BT_Interface
from config import Session_Config


def main() -> int:
    # Load session configuration
    cfg = Session_Config()

    # Create Bluetooth interface
    bt = BT_Interface()

    # Initialize Bluetooth interface
    print(bt.power_off())
    print(bt.power_on())
    # print(bt.devices())
    # devices = bt.scan(duration = 20) # 15 seconds was found to be the minimum time required
    # if cfg.sink in devices:
    #     print(bt.pair(cfg.sink))
    #     print(bt.trust(cfg.sink))
    #     print(bt.connect(cfg.sink))
    #     print(bt.info(cfg.sink))

    # # Process discovered devices
    # for addr, device in devices.items():
    #     print(f"Found device: {addr} - {device}")

# Script entry point
if __name__ == "__main__":
    raise SystemExit(main())