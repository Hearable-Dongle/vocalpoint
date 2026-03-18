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

VP_FLAG_CHANGED = 1 << 0
VP_FLAG_VOL     = 1 << 2
VP_FLAG_BAT     = 1 << 3
VP_FLAG_ADDR    = 1 << 4
VP_FLAG_P1      = 1 << 5
VP_FLAG_P2      = 1 << 6
VP_FLAG_VOL_STATUS = 1 << 7

VP_REQ_ACK_CMD = 1 << 0
VP_REQ_DATA = 1 << 1
VP_REQ_VOL  = 1 << 2
VP_REQ_BAT  = 1 << 3
VP_REQ_ADDR = 1 << 4
VP_REQ_P1   = 1 << 5
VP_REQ_P2   = 1 << 6
VP_REQ_VOL_STATUS = 1 << 7
VP_REQ_ACK_STATUS_SHIFT = 1
VP_REQ_ACK_SEQ_SHIFT = 8
VP_REQ_OFFSET_SHIFT = 24

VP_PARAM_BITS = VP_FLAG_VOL | VP_FLAG_BAT | VP_FLAG_ADDR | VP_FLAG_P1 | VP_FLAG_P2 | VP_FLAG_VOL_STATUS

VP_VOLUME_STATUS_IDLE = 0
VP_VOLUME_STATUS_PENDING = 1
VP_VOLUME_STATUS_RECEIVED = 2
VP_VOLUME_STATUS_APPLIED = 3
VP_VOLUME_STATUS_FAILED = 4

VP_STATUS_LEN = 4
VP_RESP_HDR_LEN = 4
VP_REQ_MAILBOX_OFFSET = 0x00
VP_RESP_MAILBOX_OFFSET = 0x04
VP_RESP_MAILBOX_LEN = 28
VP_RESP_PAYLOAD_MAX = VP_RESP_MAILBOX_LEN - VP_RESP_HDR_LEN

PARAM_PAYLOAD_SIZES: dict[int, int] = {
    VP_FLAG_VOL:  3,
    VP_FLAG_BAT:  1,
    VP_FLAG_ADDR: 40,
    VP_FLAG_P1:   32,
    VP_FLAG_P2:   32,
    VP_FLAG_VOL_STATUS: 5,
}

PARAM_FLAG_TO_FIELD: dict[int, str] = {
    VP_FLAG_VOL:  "volume",
    VP_FLAG_BAT:  "battery",
    VP_FLAG_ADDR: "ble_addr",
    VP_FLAG_P1:   "param1",
    VP_FLAG_P2:   "param2",
    VP_FLAG_VOL_STATUS: "volume_status",
}

SETTLE_SEC = 0.020
INTER_TRANSACTION_SEC = 0.005
STATUS_RETRY_COUNT = 3
PARAM_RETRY_COUNT = 3


@dataclass
class DeviceState:
    volume: int = 0
    battery: int = 0
    volume_seq: int = 0
    volume_ack_seq: int = 0
    volume_status: int = VP_VOLUME_STATUS_IDLE
    ble_addr: str = ""
    param1: str = ""
    param2: str = ""


def _write_request(bus: SMBus, address: int, flags: int) -> None:
    data = bytes([VP_REQ_MAILBOX_OFFSET]) + struct.pack("<I", flags)
    bus.i2c_rdwr(i2c_msg.write(address, data))


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


def _ack_request(seq: int, status: int) -> int:
    return (
        VP_REQ_ACK_CMD
        | ((status & 0x7) << VP_REQ_ACK_STATUS_SHIFT)
        | ((seq & 0xFFFF) << VP_REQ_ACK_SEQ_SHIFT)
    )


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
        state.volume = raw[0]
        state.volume_seq = int.from_bytes(raw[1:3], "little")
    elif param_bit == VP_FLAG_BAT:
        state.battery = _decode_u8(raw)
    elif param_bit == VP_FLAG_ADDR:
        state.ble_addr = _decode_string(raw)
    elif param_bit == VP_FLAG_P1:
        state.param1 = _decode_string(raw)
    elif param_bit == VP_FLAG_P2:
        state.param2 = _decode_string(raw)
    elif param_bit == VP_FLAG_VOL_STATUS:
        state.volume_status = raw[0]
        state.volume_seq = int.from_bytes(raw[1:3], "little")
        state.volume_ack_seq = int.from_bytes(raw[3:5], "little")


def write_volume_ack(bus: SMBus, address: int, seq: int, status: int) -> None:
    _write_request(bus, address, _ack_request(seq, status))


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
    args = parser.parse_args()

    print(
        f"VocalPoint I2C  bus={args.bus} addr=0x{args.address:02X} "
        f"interval={args.interval_ms}ms  protocol=mailbox"
    )

    state = DeviceState()
    last_persisted: dict[str, object] | None = None
    pending_dirty = 0

    with SMBus(args.bus) as bus:
        while True:
            cycle_start = time.monotonic()
            try:
                flags = read_status(bus, args.address)

                if flags & VP_FLAG_CHANGED:
                    pending_dirty |= (flags & VP_PARAM_BITS)

                changed = False
                for param_bit in (
                    VP_FLAG_VOL,
                    VP_FLAG_BAT,
                    VP_FLAG_ADDR,
                    VP_FLAG_P1,
                    VP_FLAG_P2,
                    VP_FLAG_VOL_STATUS,
                ):
                    if not (pending_dirty & param_bit):
                        continue

                    try:
                        raw = read_param(bus, args.address, param_bit)
                        apply_param(state, param_bit, raw)
                        pending_dirty &= ~param_bit
                        if (
                            param_bit == VP_FLAG_VOL
                            and state.volume_seq > state.volume_ack_seq
                        ):
                            write_volume_ack(
                                bus,
                                args.address,
                                state.volume_seq,
                                VP_VOLUME_STATUS_RECEIVED,
                            )
                            state.volume_ack_seq = state.volume_seq
                            state.volume_status = VP_VOLUME_STATUS_RECEIVED
                        changed = True
                    except (ValueError, OSError) as exc:
                        print(f"I2C failed (write or read): {exc}")

                    break

                if changed:
                    current = asdict(state)
                    if current != last_persisted:
                        if args.json:
                            print(json.dumps(current, separators=(",", ":")))
                        else:
                            print(
                                f"volume={state.volume} volume_seq={state.volume_seq} "
                                f"volume_ack_seq={state.volume_ack_seq} volume_status={state.volume_status} "
                                f"battery={state.battery} "
                                f"addr='{state.ble_addr}' "
                                f"p1='{state.param1}' p2='{state.param2}'"
                            )
                        last_persisted = current

            except KeyboardInterrupt:
                print("\nStopped.")
                return 0
            except OSError as exc:
                print(f"I2C failed (write or read): {exc}")
            except Exception as exc:
                print(f"unexpected error: {exc}")

            elapsed = time.monotonic() - cycle_start
            remaining = args.interval_ms / 1000.0 - elapsed
            if remaining > 0:
                time.sleep(remaining)


if __name__ == "__main__":
    raise SystemExit(main())
