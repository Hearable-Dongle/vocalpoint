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
    assert bt.power_off(), "Failed to power off Bluetooth"
    assert bt.power_on(), "Failed to power on Bluetooth"
    assert bt.agent_on(), "Failed to enable Bluetooth agent"

    # Scan for devices and connect to configured sink
    devices = bt.scan(duration = 15) # 15 seconds was found to be the minimum time required
    assert cfg.sink in devices, f"Device {cfg.sink} not found during scan"
    assert bt.pair(cfg.sink), f"Failed to pair with device {cfg.sink}"
    assert bt.trust(cfg.sink), f"Failed to trust device {cfg.sink}"
    assert bt.connect(cfg.sink), f"Failed to connect to device {cfg.sink}"

    # Print Bluetooth sink information
    print(bt.info(cfg.sink))

# Script entry point
if __name__ == "__main__":
    raise SystemExit(main())