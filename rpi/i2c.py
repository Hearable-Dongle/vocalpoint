#!/usr/bin/env python3
"""
Raspberry Pi I2C master for the ESP32 VocalPoint mailbox bridge.

Protocol overview
-----------------
The ESP32 exposes two I2C RAM mailboxes:
  request mailbox  at offset 0x00 (4 bytes)
  response mailbox at offset 0x04 (28 bytes)

The RPi writes a 32-bit request register into the request mailbox, waits
SETTLE_SEC, then reads the response mailbox. Long string parameters are fetched
in multiple chunks by setting the request offset in bits 24..31.
"""

from __future__ import annotations

import argparse
import json
import struct
import time
from dataclasses import asdict, dataclass

from smbus2 import SMBus, i2c_msg

# ── Protocol constants (must match i2c_protocol.h) ──────────────────────────

VP_FLAG_CHANGED                 = 1 << 0
VP_FLAG_VOL                     = 1 << 2
VP_FLAG_VOICE_PROFILE_NUM       = 1 << 3
VP_FLAG_BLE_UUID_ADDR           = 1 << 4
VP_FLAG_AUDIO_OUT_NAME          = 1 << 5
VP_FLAG_WIFI_SSID               = 1 << 6
VP_FLAG_WIFI_PWD                = 1 << 7

VP_REQ_DATA                     = 1 << 1
VP_REQ_VOL                      = 1 << 2
VP_REQ_VOICE_PROFILE_NUM        = 1 << 3
VP_REQ_BLE_UUID_ADDR            = 1 << 4
VP_REQ_AUDIO_OUT_NAME           = 1 << 5
VP_REQ_WIFI_SSID                = 1 << 6
VP_REQ_WIFI_PWD                 = 1 << 7
VP_REQ_WRITE                    = 1 << 8
VP_REQ_WRITE_VOICE_PROFILE      = 1 << 9
VP_REQ_WRITE_AUDIO_OUT_NAME     = VP_REQ_AUDIO_OUT_NAME
VP_REQ_OFFSET_SHIFT             = 24

VP_PARAM_BITS = (
    VP_FLAG_VOL
    | VP_FLAG_VOICE_PROFILE_NUM
    | VP_FLAG_BLE_UUID_ADDR
    | VP_FLAG_AUDIO_OUT_NAME
    | VP_FLAG_WIFI_SSID
    | VP_FLAG_WIFI_PWD
)

VP_STATUS_LEN = 4
VP_RESP_HDR_LEN = 4
VP_REQ_MAILBOX_OFFSET = 0x00
VP_RESP_MAILBOX_OFFSET = 0x04
VP_RESP_MAILBOX_LEN = 28
VP_RESP_PAYLOAD_MAX = VP_RESP_MAILBOX_LEN - VP_RESP_HDR_LEN
VP_WRITE_MAILBOX_OFFSET = VP_RESP_MAILBOX_OFFSET
VP_WRITE_MAILBOX_LEN = VP_RESP_MAILBOX_LEN

PARAM_PAYLOAD_SIZES: dict[int, int] = {
    VP_FLAG_VOL:  1,
    VP_FLAG_VOICE_PROFILE_NUM:  1,
    VP_FLAG_BLE_UUID_ADDR: 40,
    VP_FLAG_AUDIO_OUT_NAME: 32,
    VP_FLAG_WIFI_SSID:   32,
    VP_FLAG_WIFI_PWD:    32,
}

PARAM_FLAG_TO_FIELD: dict[int, str] = {
    VP_FLAG_VOL:                "volume",
    VP_FLAG_VOICE_PROFILE_NUM:  "voice_profile_num",
    VP_FLAG_BLE_UUID_ADDR:      "ble_uuid_addr",
    VP_FLAG_AUDIO_OUT_NAME:     "audio_out_name",
    VP_FLAG_WIFI_SSID:          "wifi_ssid",
    VP_FLAG_WIFI_PWD:           "wifi_pwd",
}

SETTLE_SEC = 0.020
INTER_TRANSACTION_SEC = 0.005
STATUS_RETRY_COUNT = 3
PARAM_RETRY_COUNT = 3

AUDIO_OUT_INTERVAL_SEC = 1.4

VOICE_PROFILE_INTERVAL_SEC = 5.0

VOICE_TEST_NAMES = (
    "Tegan",
    "Ryan",
    "Matthew",
    "Tyler",
    "Jenny"
)

AUDIO_OUT_TEST_NAMES = (
    "Speaker",
    "Headphones",
    "AirPods",
    "AirPods Mini",
    "Bluetooth Speaker"
)

@dataclass
class DeviceState:
    volume: int = 0
    voice_profile_num: int = 0
    ble_uuid_addr: str = ""
    audio_out_name: str = ""
    wifi_ssid: str = ""
    wifi_pwd: str = ""


def _write_request(bus: SMBus, address: int, flags: int) -> None:
    data = bytes([VP_REQ_MAILBOX_OFFSET]) + struct.pack("<I", flags)
    bus.i2c_rdwr(i2c_msg.write(address, data))


def _write_mailbox(bus: SMBus, address: int, offset: int, payload: bytes) -> None:
    bus.i2c_rdwr(i2c_msg.write(address, bytes([offset]) + payload))


def _read_mailbox(bus: SMBus, address: int, offset: int, n: int) -> bytes:
    offset_msg = i2c_msg.write(address, [offset])
    read_msg = i2c_msg.read(address, n)
    bus.i2c_rdwr(offset_msg, read_msg)
    return bytes(read_msg)


def _expect_exact_flags(resp_flags: int, expected_flags: int, kind: str) -> None:
    if resp_flags != expected_flags:
        raise ValueError(
            f"{kind} flags mismatch: expected 0x{expected_flags:08X} got 0x{resp_flags:08X}"
        )

def _req_with_offset(param_bit: int, offset: int) -> int:
    return VP_REQ_DATA | param_bit | ((offset & 0xFF) << VP_REQ_OFFSET_SHIFT)


def write_voice_profile_name(bus: SMBus, address: int, voice_name: str) -> None:
    encoded = voice_name.encode("utf-8")[: VP_WRITE_MAILBOX_LEN - 1]
    payload = encoded + b"\x00"
    payload = payload.ljust(VP_WRITE_MAILBOX_LEN, b"\x00")

    _write_mailbox(bus, address, VP_WRITE_MAILBOX_OFFSET, payload)
    _write_request(bus, address, VP_REQ_WRITE | VP_REQ_WRITE_VOICE_PROFILE)

def announce_audio_out_name(bus: SMBus, address: int, audio_out_name: str) -> None:
    encoded = audio_out_name.encode("utf-8")[: VP_WRITE_MAILBOX_LEN - 1]
    payload = encoded + b"\x00"
    payload = payload.ljust(VP_WRITE_MAILBOX_LEN, b"\x00")

    _write_mailbox(bus, address, VP_WRITE_MAILBOX_OFFSET, payload)
    _write_request(bus, address, VP_REQ_WRITE | VP_REQ_WRITE_AUDIO_OUT_NAME)

def read_status(bus: SMBus, address: int) -> int:
    last_err: ValueError | None = None

    for _ in range(STATUS_RETRY_COUNT + 1):
        _write_request(bus, address, 0x00000000)
        time.sleep(SETTLE_SEC)
        raw = _read_mailbox(bus, address, VP_RESP_MAILBOX_OFFSET, VP_STATUS_LEN)
        flags = struct.unpack("<I", raw)[0]

        if flags & VP_REQ_DATA:
            last_err = ValueError(f"status read returned param header: 0x{flags:08X}")
            time.sleep(INTER_TRANSACTION_SEC)
            continue

        return flags

    raise last_err  # type: ignore[misc]


def read_param(bus: SMBus, address: int, param_bit: int) -> bytes:
    payload_size = PARAM_PAYLOAD_SIZES[param_bit]
    collected = bytearray()
    offset = 0

    while offset < payload_size:
        expected = _req_with_offset(param_bit, offset)
        chunk_size = min(VP_RESP_PAYLOAD_MAX, payload_size - offset)
        total = VP_RESP_HDR_LEN + chunk_size
        last_err: ValueError | None = None

        for _ in range(PARAM_RETRY_COUNT + 1):
            _write_request(bus, address, expected)
            time.sleep(SETTLE_SEC)

            raw = _read_mailbox(bus, address, VP_RESP_MAILBOX_OFFSET, total)
            resp_flags = struct.unpack("<I", raw[:VP_RESP_HDR_LEN])[0]
            try:
                _expect_exact_flags(resp_flags, expected, "param response")
            except ValueError as exc:
                last_err = exc
                time.sleep(INTER_TRANSACTION_SEC)
                continue

            collected.extend(raw[VP_RESP_HDR_LEN:])
            offset += chunk_size
            time.sleep(INTER_TRANSACTION_SEC)
            break
        else:
            raise last_err  # type: ignore[misc]

    return bytes(collected)


def _decode_u8(raw: bytes) -> int:
    return raw[0]


def _decode_string(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def apply_param(state: DeviceState, param_bit: int, raw: bytes) -> None:
    if param_bit == VP_FLAG_VOL:
        state.volume = _decode_u8(raw)
    elif param_bit == VP_FLAG_VOICE_PROFILE_NUM:
        state.voice_profile_num = _decode_u8(raw)
    elif param_bit == VP_FLAG_BLE_UUID_ADDR:
        state.ble_uuid_addr = _decode_string(raw)
    elif param_bit == VP_FLAG_AUDIO_OUT_NAME:
        state.audio_out_name = _decode_string(raw)
    elif param_bit == VP_FLAG_WIFI_SSID:
        state.wifi_ssid = _decode_string(raw)
    elif param_bit == VP_FLAG_WIFI_PWD:
        state.wifi_pwd = _decode_string(raw)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Poll ESP32 VocalPoint state over I2C (mailbox protocol)."
    )
    parser.add_argument("--bus", type=int, default=1, help="I2C bus number (default: 1)")
    parser.add_argument(
        "--address",
        type=lambda x: int(x, 0),
        default=0x42,
        help="7-bit I2C slave address (default: 0x42)",
    )
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=100,
        help="Status poll interval in milliseconds (default: 100)",
    )
    parser.add_argument("--json", action="store_true", help="Print decoded state as JSON")
    parser.add_argument(
        "--no-voice-test",
        action="store_true",
        help="Disable the periodic dummy voice-profile write test",
    )
    args = parser.parse_args()

    print(
        f"VocalPoint I2C  bus={args.bus} addr=0x{args.address:02X} "
        f"interval={args.interval_ms}ms  protocol=mailbox"
    )

    state = DeviceState()
    last_persisted: dict[str, object] | None = None
    pending_dirty = 0

    next_dummy_profile_name_write = time.monotonic()
    next_dummy_profile_name_index = 0

    next_dummy_audio_out_write = time.monotonic()
    next_dummy_audio_out_index = 0

    with SMBus(args.bus) as bus:
        while True:
            cycle_start = time.monotonic()
            try:
                now = time.monotonic()
                if not args.no_voice_test:
                    if now >= next_dummy_audio_out_write:
                        audio_out_name = AUDIO_OUT_TEST_NAMES[next_dummy_audio_out_index % len(AUDIO_OUT_TEST_NAMES)]
                        announce_audio_out_name(bus, args.address, audio_out_name)
                        print(f"audio_out_announce='{audio_out_name}'")
                        next_dummy_audio_out_index += 1
                        next_dummy_audio_out_write = now + AUDIO_OUT_INTERVAL_SEC

                    if now >= next_dummy_profile_name_write:
                        voice_name = VOICE_TEST_NAMES[next_dummy_profile_name_index % len(VOICE_TEST_NAMES)]
                        write_voice_profile_name(bus, args.address, voice_name)
                        print(f"voice_write='{voice_name}'")
                        next_dummy_profile_name_index += 1
                        next_dummy_profile_name_write = now + VOICE_PROFILE_INTERVAL_SEC


                    time.sleep(SETTLE_SEC)

                flags = read_status(bus, args.address)

                if flags & VP_FLAG_CHANGED:
                    pending_dirty |= (flags & VP_PARAM_BITS)

                changed = False
                for param_bit in (
                    VP_FLAG_VOL,
                    VP_FLAG_VOICE_PROFILE_NUM,
                    VP_FLAG_BLE_UUID_ADDR,
                    VP_FLAG_AUDIO_OUT_NAME,
                    VP_FLAG_WIFI_SSID,
                    VP_FLAG_WIFI_PWD,
                ):
                    if not (pending_dirty & param_bit):
                        continue

                    try:
                        raw = read_param(bus, args.address, param_bit)
                        apply_param(state, param_bit, raw)
                        pending_dirty &= ~param_bit
                        changed = True
                    except (ValueError, OSError) as exc:
                        field_name = PARAM_FLAG_TO_FIELD.get(param_bit, f"0x{param_bit:02X}")
                        print(f"param fetch error ({field_name}): {exc}")

                    break

                if changed:
                    current = asdict(state)
                    if current != last_persisted:
                        if args.json:
                            print(json.dumps(current, separators=(",", ":")))
                        else:
                            print(
                                f"volume={state.volume} voice_profile_num={state.voice_profile_num} "
                                f"ble_uuid_addr='{state.ble_uuid_addr}' "
                                f"audio_out_name='{state.audio_out_name}' "
                                f"wifi_ssid='{state.wifi_ssid}' wifi_pwd='{state.wifi_pwd[0:16]}'"
                            )
                        last_persisted = current

            except KeyboardInterrupt:
                print("\nStopped.")
                return 0
            except OSError as exc:
                print(f"I2C error: {exc}")
            except Exception as exc:
                print(f"unexpected error: {exc}")

            elapsed = time.monotonic() - cycle_start
            remaining = args.interval_ms / 1000.0 - elapsed
            if remaining > 0:
                time.sleep(remaining)


if __name__ == "__main__":
    raise SystemExit(main())
