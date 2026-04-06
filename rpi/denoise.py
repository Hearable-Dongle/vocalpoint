from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pyrnnoise import RNNoise
import soxr


@dataclass(slots=True)
class DenoiseResult:
    denoised: np.ndarray
    residual: np.ndarray


class RNNoiseProcessor:
    def __init__(
        self,
        *,
        sample_rate_hz: int = 48000,
        frame_ms: int = 10,
        **_: object,
    ) -> None:
        self._sample_rate_hz = int(sample_rate_hz)
        self._frame_size = max(1, int(round(self._sample_rate_hz * (float(frame_ms) / 1000.0))))
        self._backend_rate_hz = 48000
        if self._sample_rate_hz not in {16000, 48000}:
            raise ValueError(f"RNNoiseProcessor only supports 16000 or 48000 Hz input, got {self._sample_rate_hz}")

        self._backend = RNNoise(self._backend_rate_hz)
        self._backend.channels = 1
        self._backend.dtype = np.int16
        self._last_inverse_output = np.zeros((0,), dtype=np.float32)
        self._last_output_sample = 0.0
        self._to_backend_stream = None
        self._from_backend_stream = None
        if self._sample_rate_hz != self._backend_rate_hz:
            self._to_backend_stream = soxr.ResampleStream(
                self._sample_rate_hz,
                self._backend_rate_hz,
                1,
                dtype="float32",
                quality="HQ",
            )
            self._from_backend_stream = soxr.ResampleStream(
                self._backend_rate_hz,
                self._sample_rate_hz,
                1,
                dtype="float32",
                quality="HQ",
            )

    def process(self, frame: np.ndarray) -> DenoiseResult:
        x = np.asarray(frame, dtype=np.float32).reshape(-1)
        if x.shape[0] == 0:
            empty = np.zeros((0,), dtype=np.float32)
            self._last_inverse_output = empty
            return DenoiseResult(denoised=empty, residual=empty)

        x_backend = self._to_backend_rate(x)
        denoised_backend = self._denoise_backend_chunk(x_backend)
        denoised = self._from_backend_rate(denoised_backend, output_len=x.shape[0])
        if denoised.size > 0:
            self._last_output_sample = float(denoised[-1])
        residual = np.asarray(x - denoised, dtype=np.float32)
        self._last_inverse_output = residual.copy()
        return DenoiseResult(denoised=denoised, residual=residual)

    def process_stream(self, audio: np.ndarray) -> DenoiseResult:
        x = np.asarray(audio, dtype=np.float32).reshape(-1)
        if x.shape[0] == 0:
            empty = np.zeros((0,), dtype=np.float32)
            self._last_inverse_output = empty
            return DenoiseResult(denoised=empty, residual=empty)

        x_backend = self._to_backend_rate(x, last=True)
        denoised_backend = self._denoise_backend_chunk(x_backend)
        denoised = self._from_backend_rate(denoised_backend, output_len=x.shape[0], last=True)
        residual = np.asarray(x - denoised, dtype=np.float32)
        self._last_inverse_output = residual.copy()
        return DenoiseResult(denoised=denoised, residual=residual)

    def get_last_inverse_output(self) -> np.ndarray:
        return self._last_inverse_output.copy()

    def _to_backend_rate(self, audio: np.ndarray, *, last: bool = False) -> np.ndarray:
        x = np.asarray(audio, dtype=np.float32).reshape(-1)
        if self._sample_rate_hz == self._backend_rate_hz:
            return x
        if self._to_backend_stream is None:
            raise RuntimeError("missing input resample stream")
        return np.asarray(self._to_backend_stream.resample_chunk(x, last=bool(last)), dtype=np.float32).reshape(-1)

    def _from_backend_rate(self, audio: np.ndarray, *, output_len: int, last: bool = False) -> np.ndarray:
        y = np.asarray(audio, dtype=np.float32).reshape(-1)
        if self._sample_rate_hz != self._backend_rate_hz:
            if self._from_backend_stream is None:
                raise RuntimeError("missing output resample stream")
            y = np.asarray(self._from_backend_stream.resample_chunk(y, last=bool(last)), dtype=np.float32).reshape(-1)
        if y.shape[0] < output_len:
            y = np.pad(y, (0, output_len - y.shape[0]), constant_values=float(self._last_output_sample))
        return np.asarray(y[:output_len], dtype=np.float32)

    def _denoise_backend_chunk(self, audio: np.ndarray) -> np.ndarray:
        x = np.asarray(audio, dtype=np.float32).reshape(-1)
        if x.size == 0:
            return np.zeros((0,), dtype=np.float32)
        chunk_i16 = np.clip(np.round(x * 32768.0), -32768.0, 32767.0).astype(np.int16, copy=False)
        parts: list[np.ndarray] = []
        for _vad_prob, den in self._backend.denoise_chunk(np.atleast_2d(chunk_i16), partial=False):
            den_arr = np.asarray(den, dtype=np.float32).reshape(-1) / 32768.0
            parts.append(np.asarray(den_arr, dtype=np.float32))
        if not parts:
            return np.zeros_like(x, dtype=np.float32)
        return np.concatenate(parts, axis=0).astype(np.float32, copy=False)
