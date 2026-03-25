#!/usr/bin/env python3
import time
from gi.repository import GLib

from bt import BT_Interface
from audio import Audio_Interface
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
    # This runs asynchronously while the main loop handles other tasks
    audio.start(callback)

    def main_loop_callback() -> bool:
        """
        Main event loop callback that runs periodically via GLib timeout.
        This is called every IDLE_SLEEP_SEC milliseconds, allowing the GLib
        event loop to process D-Bus events and other tasks between iterations.
        
        Returns True to continue scheduling, False to stop the loop.
        """
        
        try:
            cfg.logger.info("Main loop callback executing")

            # Return True to keep the timeout scheduled (non-blocking)
            return True

        except Exception as e:
            cfg.logger.error(f"Error in main loop: {e}")
            return True  # Continue running despite error

    try:
        # Schedule main loop to run every IDLE_SLEEP_SEC milliseconds
        # This is non-blocking - D-Bus events and audio streaming can process between iterations
        GLib.timeout_add(500, main_loop_callback)

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
        cfg.logger.info("Interrupted by user")
        return 0
    finally:
        audio.stop()
        # i2c.stop()


if __name__ == "__main__":
    raise SystemExit(main())
