#!/usr/bin/env python3
# Local imports
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNAL_PROCESSING_ROOT = REPO_ROOT / "signal-processing-research"

for path in (REPO_ROOT, SIGNAL_PROCESSING_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from bt import BT_Interface
from usb import USB_Interface
from config import Session_Config
from speech_enhancement_callback import process_callback_audio
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
    # Load session configuration
    cfg = Session_Config()

    # Create Bluetooth and USB interface with logger
    bt = BT_Interface(cfg.logger)
    usb = USB_Interface(cfg.logger, cfg.source, cfg.fs, cfg.frame)

    # Initialize Bluetooth interface
    assert bt.power_off()
    assert bt.power_on()
    assert bt.agent_on()

    # Connect USB interface
    assert usb.connect()

    # Scan for devices
    devices = bt.scan(duration = 15) # 15 seconds was found to be the minimum time required

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

    # Stream audio with consistent timing
    try:
        consecutive_errors = 0
        while True:
            audio_frame = usb.read_frame()
            if audio_frame is None:
                consecutive_errors += 1
                if consecutive_errors > 10:
                    cfg.logger.error("Too many consecutive read errors, stopping stream")
                    break
                continue
            
            consecutive_errors = 0
            processed_frame = callback(audio_frame, usb.channels)
            if not bt.write_audio(processed_frame):
                cfg.logger.warning("Failed to write audio frame")
    except KeyboardInterrupt:
        cfg.logger.info("Interrupted by user, shutting down...")
    except Exception as e:
        cfg.logger.error(f"Error during streaming: {e}")
    finally:
        if not bt.disconnect(cfg.sink):
            cfg.logger.error("Failed to disconnect Bluetooth device")
        if not usb.disconnect():
            cfg.logger.error("Failed to disconnect USB device")

    return 0

# Script entry point
if __name__ == "__main__":
    raise SystemExit(main())
