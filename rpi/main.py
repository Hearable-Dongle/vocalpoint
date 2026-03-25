#!/usr/bin/env python3
import time
from gi.repository import GLib

from bt import BT_Interface
from audio import Audio_Interface
from usb import USB_Interface
from config import Session_Config
from i2c import I2C_Interface
import numpy as np


def audio_callback(audio_bytes: bytes, channels: int) -> bytes:
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

def main_callback() -> bool:
    """
    Main event loop callback that runs periodically via GLib timeout.
    """
    # Try to execute the main loop callback
    try:
        cfg.logger.info("Main loop callback executing")

    # Catch any exceptions to prevent the GLib loop from stopping
    except Exception as e:
        # Log any exceptions that occur in the main loop
        cfg.logger.error(f"Error in main loop: {e}")

    finally:
        # Continue running despite error
        return True  

def main() -> int:
    cfg = Session_Config()
    cfg.logger.info("Starting Vocalpoint audio passthrough application")

    # Initialize Bluetooth, USB and I2C interfaces
    bt = BT_Interface(cfg.logger)
    usb = USB_Interface(cfg.logger, cfg.source, cfg.fs, cfg.frame)
    # i2c = I2C_Interface(autostart=True, enable_voice_test=False, emit_logs=True)
    audio = Audio_Interface(bt, usb, cfg.logger, channels=6)

    # Configure Bluetooth interface
    assert bt.power_off()
    assert bt.power_on()
    assert bt.agent_on()

    # Configure USB interface
    assert usb.connect()

    # Scan for initial devices
    devices = bt.scan(duration=15)  # 15 seconds was found to be the minimum time required

    # Get device info if sink was found
    info = {}
    if cfg.sink in devices:
        info = bt.info(cfg.sink)
        cfg.logger.info(f"Found target sink: {cfg.sink} - {info['Name']}")
    else:
        cfg.logger.info(f"Target sink not found: {cfg.sink}")
        return 1

    # Pair device if unpaired
    if not info["Paired"]:
        assert bt.pair(cfg.sink)
        cfg.logger.info(f"Paired device: {info['Name']}")

    # Trust device if untrusted
    if not info["Trusted"]:
        assert bt.trust(cfg.sink)
        cfg.logger.info(f"Trusted device: {info['Name']}")

    # Connect device if unconnected
    if not info["Connected"]:
        assert bt.connect(cfg.sink, cfg.fs)
        cfg.logger.info(f"Connected device: {info['Name']}")

    # Start audio streaming in background thread
    audio.start(audio_callback)

    try:
        # Schedule main loop to run periodically
        GLib.timeout_add(500, main_callback)

        # Create and run the main GLib event loop
        # This will:
        # - Process D-Bus events from Bluetooth adapter
        # - Run scheduled callbacks (main_loop_callback)
        # - Allow the audio streaming background thread to run
        main_loop = GLib.MainLoop()
        
        cfg.logger.info("Starting async event loop for audio passthrough")
        main_loop.run()

        return 0

    except KeyboardInterrupt:
        # Log interruption by user but not as an error
        cfg.logger.info("Interrupted by user")

    finally:
        # Ensure all interfaces are stopped and Bluetooth is disconnected on exit
        if not audio.stop() or not usb.stop() or not bt.disconnect():
            # Log if any interface did not stop cleanly
            cfg.logger.warning("One or more interfaces did not stop cleanly")

        else:
            # Log if all interfaces stopped cleanly
            cfg.logger.info("All interfaces stopped cleanly")
        # i2c.stop()


if __name__ == "__main__":
    raise SystemExit(main())
