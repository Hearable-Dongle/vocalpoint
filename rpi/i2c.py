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
import logging
import shlex
import struct
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, replace

from smbus2 import SMBus, i2c_msg
from wifi import WifiManager

# ── Protocol constants (must match i2c_protocol.h) ──────────────────────────

VP_FLAG_CHANGED                 = 1 << 0
VP_FLAG_VOL                     = 1 << 2
VP_FLAG_VOICE_PROFILE_NUM       = 1 << 3
VP_FLAG_REBOOT                  = 1 << 4
VP_FLAG_AUDIO_OUT_NAME          = 1 << 5
VP_FLAG_WIFI_SSID               = 1 << 6
VP_FLAG_WIFI_PWD                = 1 << 7

VP_REQ_DATA                     = 1 << 1
VP_REQ_VOL                      = 1 << 2
VP_REQ_VOICE_PROFILE_NUM        = 1 << 3
VP_REQ_AUDIO_OUT_NAME           = 1 << 5
VP_REQ_WIFI_SSID                = 1 << 6
VP_REQ_WIFI_PWD                 = 1 << 7
VP_REQ_WRITE                    = 1 << 8
VP_REQ_WRITE_VOICE_PROFILE      = 1 << 9
VP_REQ_ACK_REBOOT               = 1 << 10
VP_REQ_WRITE_AUDIO_OUT_NAME     = VP_REQ_AUDIO_OUT_NAME
VP_REQ_OFFSET_SHIFT             = 24

VP_FETCH_PARAM_BITS = (
    VP_FLAG_VOL
    | VP_FLAG_VOICE_PROFILE_NUM
    | VP_FLAG_AUDIO_OUT_NAME
    | VP_FLAG_WIFI_SSID
    | VP_FLAG_WIFI_PWD
)
VP_STATUS_BITS = (
    VP_FLAG_CHANGED
    | VP_FLAG_VOL
    | VP_FLAG_VOICE_PROFILE_NUM
    | VP_FLAG_REBOOT
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
    VP_FLAG_VOL: 1,
    VP_FLAG_VOICE_PROFILE_NUM: 1,
    VP_FLAG_AUDIO_OUT_NAME: 32,
    VP_FLAG_WIFI_SSID: 32,
    VP_FLAG_WIFI_PWD: 32,
}

PARAM_FLAG_TO_FIELD: dict[int, str] = {
    VP_FLAG_VOL: "volume",
    VP_FLAG_VOICE_PROFILE_NUM: "voice_profile_num",
    VP_FLAG_AUDIO_OUT_NAME: "audio_out_name",
    VP_FLAG_WIFI_SSID: "wifi_ssid",
    VP_FLAG_WIFI_PWD: "wifi_pwd",
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
    "Jenny",
)

AUDIO_OUT_TEST_NAMES = (
    "Speaker",
    "Headphones",
    "AirPods",
    "AirPods Mini",
    "Bluetooth Speaker",
)

LOGGER = logging.getLogger("vocalpoint.i2c")

@dataclass
class DeviceState:
    volume: int = 0
    voice_profile_num: int = 0
    audio_out_name: str = ""
    wifi_ssid: str = ""
    wifi_pwd: str = ""


def _configure_logger() -> logging.Logger:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    return LOGGER


def _normalized_wifi_credentials(state: DeviceState) -> tuple[str, str]:
    return (state.wifi_ssid.strip(), state.wifi_pwd.strip())


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


def write_audio_out_name(bus: SMBus, address: int, audio_out_name: str) -> None:
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
        flags = struct.unpack("<I", raw)[0] & VP_STATUS_BITS

        if flags & VP_REQ_DATA:
            last_err = ValueError(f"status read returned param header: 0x{flags:08X}")
            time.sleep(INTER_TRANSACTION_SEC)
            continue

        return flags

    raise last_err  # type: ignore[misc]


def ack_reboot_request(bus: SMBus, address: int) -> None:
    _write_request(bus, address, VP_REQ_ACK_REBOOT)
    time.sleep(SETTLE_SEC)


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
    elif param_bit == VP_FLAG_AUDIO_OUT_NAME:
        state.audio_out_name = _decode_string(raw)
    elif param_bit == VP_FLAG_WIFI_SSID:
        state.wifi_ssid = _decode_string(raw)
    elif param_bit == VP_FLAG_WIFI_PWD:
        state.wifi_pwd = _decode_string(raw)


class I2C_Interface:
    def __init__(
        self,
        bus: int = 1,
        address: int = 0x42,
        interval_ms: int = 100,
        *,
        allow_reboot: bool = False,
        reboot_command: str = "sudo systemctl reboot",
        enable_voice_test: bool = False,
        emit_logs: bool = False,
        json_output: bool = False,
        autostart: bool = False,
    ) -> None:
        self.bus_num = bus
        self.address = address
        self.interval_ms = interval_ms
        self.allow_reboot = allow_reboot
        self.reboot_command = reboot_command
        self.enable_voice_test = enable_voice_test
        self.emit_logs = emit_logs
        self.json_output = json_output

        self.state = DeviceState()
        self._state_lock = threading.Lock()
        self._pending_dirty = 0
        self._last_persisted: dict[str, object] | None = None

        self._bus = SMBus(self.bus_num)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._next_dummy_profile_name_write = time.monotonic()
        self._next_dummy_profile_name_index = 0
        self._next_dummy_audio_out_write = time.monotonic()
        self._next_dummy_audio_out_index = 0

        if autostart:
            self.start()

    def close(self) -> None:
        if self._bus is not None:
            self._bus.close()
            self._bus = None

    def __enter__(self) -> "I2C":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def get_state(self) -> DeviceState:
        with self._state_lock:
            return replace(self.state)

    def get_volume(self) -> int:
        return self.get_state().volume

    def get_voice_profile_num(self) -> int:
        return self.get_state().voice_profile_num

    def get_audio_out_name(self) -> str:
        return self.get_state().audio_out_name

    def get_wifi_ssid(self) -> str:
        return self.get_state().wifi_ssid

    def get_wifi_pwd(self) -> str:
        return self.get_state().wifi_pwd

    def write_voice_profile_name(self, voice_name: str) -> None:
        assert self._bus is not None
        write_voice_profile_name(self._bus, self.address, voice_name)

    def write_audio_out_name(self, audio_out_name: str) -> None:
        assert self._bus is not None
        write_audio_out_name(self._bus, self.address, audio_out_name)

    def ack_reboot_request(self) -> None:
        assert self._bus is not None
        ack_reboot_request(self._bus, self.address)

    def poll_once(self) -> bool:
        assert self._bus is not None
        now = time.monotonic()

        if self.enable_voice_test:
            if now >= self._next_dummy_audio_out_write:
                audio_out_name = AUDIO_OUT_TEST_NAMES[
                    self._next_dummy_audio_out_index % len(AUDIO_OUT_TEST_NAMES)
                ]
                self.write_audio_out_name(audio_out_name)
                if self.emit_logs:
                    print(f"audio_out_announce='{audio_out_name}'")
                self._next_dummy_audio_out_index += 1
                self._next_dummy_audio_out_write = now + AUDIO_OUT_INTERVAL_SEC

            if now >= self._next_dummy_profile_name_write:
                voice_name = VOICE_TEST_NAMES[
                    self._next_dummy_profile_name_index % len(VOICE_TEST_NAMES)
                ]
                self.write_voice_profile_name(voice_name)
                if self.emit_logs:
                    print(f"voice_write='{voice_name}'")
                self._next_dummy_profile_name_index += 1
                self._next_dummy_profile_name_write = now + VOICE_PROFILE_INTERVAL_SEC

            time.sleep(SETTLE_SEC)

        flags = read_status(self._bus, self.address)

        if flags & VP_FLAG_REBOOT:
            if self.emit_logs:
                print("reboot request received from ESP32")
            self.ack_reboot_request()
            if self.allow_reboot:
                if self.emit_logs:
                    print(f"executing reboot command: {self.reboot_command}")
                subprocess.Popen(shlex.split(self.reboot_command))
                return False
            if self.emit_logs:
                print("reboot command skipped (run with --allow-reboot to execute it)")
            time.sleep(INTER_TRANSACTION_SEC)
            return False

        if flags & VP_FLAG_CHANGED:
            self._pending_dirty |= (flags & VP_FETCH_PARAM_BITS)

        changed = False
        for param_bit in (
            VP_FLAG_VOL,
            VP_FLAG_VOICE_PROFILE_NUM,
            VP_FLAG_AUDIO_OUT_NAME,
            VP_FLAG_WIFI_SSID,
            VP_FLAG_WIFI_PWD,
        ):
            if not (self._pending_dirty & param_bit):
                continue

            try:
                raw = read_param(self._bus, self.address, param_bit)
                with self._state_lock:
                    apply_param(self.state, param_bit, raw)
                self._pending_dirty &= ~param_bit
                changed = True
            except (ValueError, OSError) as exc:
                if self.emit_logs:
                    field_name = PARAM_FLAG_TO_FIELD.get(param_bit, f"0x{param_bit:02X}")
                    print(f"param fetch error ({field_name}): {exc}")
            break

        if not changed:
            return False

        current = asdict(self.get_state())
        if current == self._last_persisted:
            return False

        self._last_persisted = current
        if self.emit_logs:
            if self.json_output:
                print(json.dumps(current, separators=(",", ":")))
            else:
                state = self.get_state()
                print(
                    f"volume={state.volume} voice_profile_num={state.voice_profile_num} "
                    f"audio_out_name='{state.audio_out_name}' "
                    f"wifi_ssid='{state.wifi_ssid}' wifi_pwd='{state.wifi_pwd[0:16]}'"
                )

        return True

    def run(self) -> None:
        while not self._stop_event.is_set():
            cycle_start = time.monotonic()
            try:
                self.poll_once()
            except OSError as exc:
                if self.emit_logs:
                    print(f"I2C error: {exc}")
            except Exception as exc:
                if self.emit_logs:
                    print(f"unexpected error: {exc}")

            remaining = self.interval_ms / 1000.0 - (time.monotonic() - cycle_start)
            if remaining > 0:
                self._stop_event.wait(remaining)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run, daemon=True, name="vocalpoint-i2c")
        self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout)
        self.close()


def main() -> int:
    logger = _configure_logger()
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
        "--allow-reboot",
        action="store_true",
        help="Allow a pending ESP32 reboot request to execute the local reboot command",
    )
    parser.add_argument(
        "--reboot-command",
        default="sudo systemctl reboot",
        help="Command to run when --allow-reboot is set (default: 'sudo systemctl reboot')",
    )
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

    controller = I2C_Interface(
        bus=args.bus,
        address=args.address,
        interval_ms=args.interval_ms,
        allow_reboot=args.allow_reboot,
        reboot_command=args.reboot_command,
        enable_voice_test=not args.no_voice_test,
        emit_logs=True,
        json_output=args.json,
    )

    try:
        controller.run()
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        controller.stop()

    return 0
    state = DeviceState()
    wifi_manager = WifiManager(logger)
    last_persisted: dict[str, object] | None = None
    last_wifi_request = ("", "")
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

                if flags & VP_FLAG_REBOOT:
                    print("reboot request received from ESP32")
                    ack_reboot_request(bus, args.address)
                    if args.allow_reboot:
                        print(f"executing reboot command: {args.reboot_command}")
                        subprocess.Popen(shlex.split(args.reboot_command))
                        return 0
                    print("reboot command skipped (run with --allow-reboot to execute it)")
                    time.sleep(INTER_TRANSACTION_SEC)
                    continue

                if flags & VP_FLAG_CHANGED:
                    pending_dirty |= (flags & VP_FETCH_PARAM_BITS)

                changed = False
                for param_bit in (
                    VP_FLAG_VOL,
                    VP_FLAG_VOICE_PROFILE_NUM,
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
                    current_wifi_request = _normalized_wifi_credentials(state)
                    if current_wifi_request != last_wifi_request:
                        last_wifi_request = current_wifi_request
                        wifi_ssid, wifi_pwd = current_wifi_request
                        if wifi_ssid and wifi_pwd:
                            wifi_result = wifi_manager.connect_from_i2c(
                                wifi_ssid,
                                wifi_pwd,
                            )
                            print(wifi_result)

                    current = asdict(state)
                    if current != last_persisted:
                        if args.json:
                            print(json.dumps(current, separators=(",", ":")))
                        else:
                            print(
                                f"volume={state.volume} voice_profile_num={state.voice_profile_num} "
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
