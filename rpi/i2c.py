"""
Raspberry Pi I2C master for the ESP32 VocalPoint mailbox bridge.
"""

from __future__ import annotations

import logging
import struct
import subprocess
import threading
import time
from dataclasses import dataclass, replace
from typing import Optional

from smbus2 import SMBus, i2c_msg


# These bit flags must match the ESP32 project
VP_FLAG_CHANGED = 1 << 0
VP_FLAG_VOL = 1 << 2

VP_REQ_DATA = 1 << 1
VP_REQ_VOL = 1 << 2
VP_REQ_OFFSET_SHIFT = 24

VP_FETCH_PARAM_STATUS_BITS = (
    VP_FLAG_VOL
)

VP_STATUS_BITS = (
    VP_FLAG_CHANGED
    | VP_FLAG_VOL
)

VP_STATUS_LEN = 4
VP_RESP_HDR_LEN = 4
VP_REQ_MAILBOX_OFFSET = 0x00
VP_RESP_MAILBOX_OFFSET = 0x04
VP_RESP_MAILBOX_LEN = 28
VP_RESP_PAYLOAD_MAX = VP_RESP_MAILBOX_LEN - VP_RESP_HDR_LEN

PARAM_PAYLOAD_SIZES: dict[int, int] = {
    VP_FLAG_VOL: 1,
}

PARAM_FLAG_TO_REQ: dict[int, int] = {
    VP_FLAG_VOL: VP_REQ_VOL,
}

SETTLE_SEC = 0.020
INTER_TRANSACTION_SEC = 0.005
STATUS_RETRY_COUNT = 3
PARAM_RETRY_COUNT = 3

@dataclass
class DeviceState:
    volume: int = 0


class I2C_Interface:
    """
    Interface for ESP32 mailbox communication over I2C.
    """

    __FAILURE_THRESHOLD: int = 5

    def __init__(
        self,
        logger: logging.Logger,
        bus: int = 1,
        address: int = 0x42,
        interval_ms: int = 100,
        *,
        emit_logs: bool = False,
        autostart: bool = False,
    ) -> None:
        self.__logger = logger
        self.__bus_num = bus
        self.__address = address
        self.__interval_ms = interval_ms
        self.__emit_logs = emit_logs

        self.__state = DeviceState()
        self.__state_lock = threading.Lock()
        self.__pending_dirty = 0

        self.__stop_event = threading.Event()
        self.__thread: Optional[threading.Thread] = None
        self.__bus: Optional[SMBus] = None

        self.__hardfault = False
        self.__consecutive_failures = 0

        try:
            self.__bus = SMBus(self.__bus_num)
            self.__logger.info("I2C Interface initialized")
            if autostart:
                self.start()
        except Exception as e:
            self.__logger.error(f"Failed to initialize I2C interface: {e}")
            self.__hardfault = True

    def __log(self, message: str) -> None:
        if self.__emit_logs:
            self.__logger.info(message)

    def __change_volume(self, new_volume: int) -> None:
        volume = max(0, min(100, int(new_volume)))
        try:
            subprocess.run(
                ["amixer", "set", "Master", f"{volume}%"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            self.__logger.warning(f"Failed to set volume: {exc.stderr or exc}")

    def __write_request(self, flags: int) -> None:
        assert self.__bus is not None
        data = bytes([VP_REQ_MAILBOX_OFFSET]) + struct.pack("<I", flags)
        self.__bus.i2c_rdwr(i2c_msg.write(self.__address, data))

    def __write_mailbox(self, offset: int, payload: bytes) -> None:
        assert self.__bus is not None
        self.__bus.i2c_rdwr(i2c_msg.write(self.__address, bytes([offset]) + payload))

    def __read_mailbox(self, offset: int, n: int) -> bytes:
        assert self.__bus is not None
        offset_msg = i2c_msg.write(self.__address, [offset])
        read_msg = i2c_msg.read(self.__address, n)
        self.__bus.i2c_rdwr(offset_msg, read_msg)
        return bytes(read_msg)

    def __expect_exact_flags(self, resp_flags: int, expected_flags: int, kind: str) -> None:
        if resp_flags != expected_flags:
            raise ValueError(
                f"{kind} flags mismatch: expected 0x{expected_flags:08X} got 0x{resp_flags:08X}"
            )

    def __req_with_offset(self, param_bit: int, offset: int) -> int:
        return VP_REQ_DATA | param_bit | ((offset & 0xFF) << VP_REQ_OFFSET_SHIFT)

    def __read_status(self) -> int:
        last_err: Optional[ValueError] = None

        for _ in range(STATUS_RETRY_COUNT + 1):
            self.__write_request(0x00000000)
            time.sleep(SETTLE_SEC)
            raw = self.__read_mailbox(VP_RESP_MAILBOX_OFFSET, VP_STATUS_LEN)
            flags = struct.unpack("<I", raw)[0] & VP_STATUS_BITS

            if flags & VP_REQ_DATA:
                last_err = ValueError(f"status read returned param header: 0x{flags:08X}")
                time.sleep(INTER_TRANSACTION_SEC)
                continue

            return flags

        raise last_err if last_err else ValueError("Failed to read status")

    def __read_param(self, param_bit: int) -> bytes:
        payload_size = PARAM_PAYLOAD_SIZES[param_bit]
        request_bit = PARAM_FLAG_TO_REQ[param_bit]
        collected = bytearray()
        offset = 0

        while offset < payload_size:
            expected = self.__req_with_offset(request_bit, offset)
            chunk_size = min(VP_RESP_PAYLOAD_MAX, payload_size - offset)
            total = VP_RESP_HDR_LEN + chunk_size
            last_err: Optional[ValueError] = None

            for _ in range(PARAM_RETRY_COUNT + 1):
                self.__write_request(expected)
                time.sleep(SETTLE_SEC)

                raw = self.__read_mailbox(VP_RESP_MAILBOX_OFFSET, total)
                resp_flags = struct.unpack("<I", raw[:VP_RESP_HDR_LEN])[0]
                try:
                    self.__expect_exact_flags(resp_flags, expected, "param response")
                except ValueError as exc:
                    last_err = exc
                    time.sleep(INTER_TRANSACTION_SEC)
                    continue

                collected.extend(raw[VP_RESP_HDR_LEN:])
                offset += chunk_size
                time.sleep(INTER_TRANSACTION_SEC)
                break
            else:
                raise last_err if last_err else ValueError("Failed to read parameter")

        return bytes(collected)

    def __decode_u8(self, raw: bytes) -> int:
        return raw[0]

    def __apply_param(self, param_bit: int, raw: bytes) -> None:
        if param_bit == VP_FLAG_VOL:
            self.__state.volume = self.__decode_u8(raw)

    def get_state(self) -> DeviceState:
        with self.__state_lock:
            return replace(self.__state)

    def get_volume(self) -> int:
        return self.get_state().volume

    def poll_once(self) -> bool:
        if self.__bus is None:
            self.__logger.error("I2C bus unavailable")
            self.__hardfault = True
            return False

        flags = self.__read_status()

        if flags & VP_FLAG_CHANGED:
            self.__pending_dirty |= (flags & VP_FETCH_PARAM_STATUS_BITS)

        changed = False
        for param_bit in (
            VP_FLAG_VOL,
        ):
            if not (self.__pending_dirty & param_bit):
                continue

            previous_volume = self.get_volume()
            raw = self.__read_param(param_bit)
            with self.__state_lock:
                self.__apply_param(param_bit, raw)
                new_volume = self.__state.volume

            if param_bit == VP_FLAG_VOL and new_volume != previous_volume:
                self.__change_volume(new_volume)

            self.__pending_dirty &= ~param_bit
            changed = True
            break

        return changed

    def __run(self) -> None:
        while not self.__stop_event.is_set():
            cycle_start = time.monotonic()
            try:
                self.poll_once()
                self.__consecutive_failures = 0
            except Exception as e:
                self.__logger.error(f"I2C polling error: {e}")
                self.__consecutive_failures += 1
                if self.__consecutive_failures >= self.__FAILURE_THRESHOLD:
                    self.__hardfault = True

            remaining = self.__interval_ms / 1000.0 - (time.monotonic() - cycle_start)
            if remaining > 0:
                self.__stop_event.wait(remaining)

    def start(self) -> bool:
        if self.__thread is not None and self.__thread.is_alive():
            self.__logger.info("I2C polling already running")
            return True

        if self.__bus is None:
            self.__logger.error("Cannot start I2C polling: bus unavailable")
            self.__hardfault = True
            return False

        self.__stop_event.clear()
        self.__thread = threading.Thread(target=self.__run, daemon=True, name="vocalpoint-i2c")
        self.__thread.start()
        self.__logger.info("I2C polling started")
        return True

    def stop(self, timeout: Optional[float] = None) -> bool:
        self.__stop_event.set()
        if self.__thread is not None and self.__thread.is_alive():
            self.__thread.join(timeout)

        if self.__bus is not None:
            self.__bus.close()
            self.__bus = None

        self.__logger.info("I2C interface stopped")
        return True

    @property
    def hardfault(self) -> bool:
        return self.__hardfault
