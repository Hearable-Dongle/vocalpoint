#!/usr/bin/env python3
# Local imports
from bt import BT_Interface
from config import Session_Config


def main() -> int:
    # Load session configuration
    cfg = Session_Config()

    # Create Bluetooth interface with logger
    bt = BT_Interface(cfg.logger)

    # Initialize Bluetooth interface
    assert bt.power_off()
    assert bt.power_on()
    assert bt.agent_on()

    # Scan for devices and connect to configured sink
    devices = bt.scan(duration = 15) # 15 seconds was found to be the minimum time required
    assert cfg.sink in devices
    assert bt.pair(cfg.sink)
    assert bt.trust(cfg.sink)
    assert bt.connect(cfg.sink)

    # Print Bluetooth sink information
    print(bt.info(cfg.sink))

# Script entry point
if __name__ == "__main__":
    raise SystemExit(main())