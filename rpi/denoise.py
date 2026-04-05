from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, iirnotch, sosfilt, tf2sos

try:
    from pyrnnoise import RNNoise as PyRNNoise  # type: ignore
except ImportError:  # pragma: no cover
    PyRNNoise = None


def _peaking_eq_sos(*, center_hz: float, q: float, gain_db: float, fs_hz: float) -> np.ndarray | None:
    center = float(center_hz)
    fs = float(fs_hz)
    quality = float(max(q, 1e-3))
    gain = float(gain_db)
    if abs(gain) <= 1e-6 or center <= 0.0 or center >= 0.5 * fs:
        return None
    a = float(10.0 ** (gain / 40.0))
    w0 = float(2.0 * np.pi * center / fs)
    alpha = float(np.sin(w0) / (2.0 * quality))
    cos_w0 = float(np.cos(w0))
    b0 = 1.0 + (alpha * a)
    b1 = -2.0 * cos_w0
    b2 = 1.0 - (alpha * a)
    a0 = 1.0 + (alpha / a)
    a1 = -2.0 * cos_w0
    a2 = 1.0 - (alpha / a)
    return tf2sos(
        np.asarray([b0 / a0, b1 / a0, b2 / a0], dtype=np.float64),
        np.asarray([1.0, a1 / a0, a2 / a0], dtype=np.float64),
    )


@dataclass(slots=True)
class DenoiseResult:
    denoised: np.ndarray
    residual: np.ndarray


class RNNoiseProcessor:
    def __init__(
        self,
        *,
        sample_rate_hz: int = 16000,
        frame_ms: int = 10,
        wet_mix: float = 0.9,
        input_gain_db: float = 0.0,
        input_highpass_enabled: bool = True,
        input_highpass_cutoff_hz: float = 80.0,
        output_highpass_enabled: bool = True,
        output_highpass_cutoff_hz: float = 80.0,
        output_lowpass_cutoff_hz: float = 0.0,
        output_notch_freq_hz: float = 0.0,
        output_notch_q: float = 0.0,
        vad_adaptive_blend_enabled: bool = True,
        vad_blend_gamma: float = 0.5,
        vad_min_speech_preserve: float = 0.15,
        vad_max_speech_preserve: float = 0.95,
        startup_warmup_enabled: bool = False,
        startup_warmup_frames: int = 10,
        chunk_crossfade_enabled: bool = False,
        chunk_crossfade_samples: int = 16,
        declick_enabled: bool = False,
        declick_alpha: float = 0.92,
        declick_conditional: bool = True,
        declick_spike_threshold: float = 0.03,
        output_clip_guard_enabled: bool = False,
        output_clip_guard_abs_max: float = 0.95,
        corruption_guard_enabled: bool = False,
        corruption_guard_rms_ratio_threshold: float = 2.0,
        corruption_guard_peak_ratio_threshold: float = 3.0,
        corruption_guard_mode: str = "hold_previous",
        voice_eq_enabled: bool = False,
        voice_eq_presence_gain_db: float = 0.0,
        voice_eq_presence_center_hz: float = 3000.0,
        voice_eq_presence_q: float = 0.9,
        voice_eq_lowmid_gain_db: float = 0.0,
        voice_eq_lowmid_center_hz: float = 300.0,
        voice_eq_lowmid_q: float = 0.8,
    ) -> None:
        if PyRNNoise is None:
            raise RuntimeError("RNNoise processor requested but pyrnnoise is unavailable.")
        self._sample_rate_hz = int(sample_rate_hz)
        self._frame_size = max(1, int(round(self._sample_rate_hz * (float(frame_ms) / 1000.0))))
        self._wet_mix = float(np.clip(wet_mix, 0.0, 1.0))
        self._input_gain_db = float(input_gain_db)
        self._vad_adaptive_blend_enabled = bool(vad_adaptive_blend_enabled)
        self._vad_blend_gamma = float(max(vad_blend_gamma, 1e-6))
        self._vad_min_speech_preserve = float(np.clip(vad_min_speech_preserve, 0.0, 1.0))
        self._vad_max_speech_preserve = float(np.clip(vad_max_speech_preserve, self._vad_min_speech_preserve, 1.0))
        self._chunk_crossfade_enabled = bool(chunk_crossfade_enabled)
        self._chunk_crossfade_samples = max(0, int(chunk_crossfade_samples))
        self._declick_enabled = bool(declick_enabled)
        self._declick_alpha = float(np.clip(declick_alpha, 0.0, 0.9999))
        self._declick_conditional = bool(declick_conditional)
        self._declick_spike_threshold = float(max(declick_spike_threshold, 0.0))
        self._output_clip_guard_enabled = bool(output_clip_guard_enabled)
        self._output_clip_guard_abs_max = float(max(output_clip_guard_abs_max, 0.0))
        self._corruption_guard_enabled = bool(corruption_guard_enabled)
        self._corruption_guard_rms_ratio_threshold = float(corruption_guard_rms_ratio_threshold)
        self._corruption_guard_peak_ratio_threshold = float(corruption_guard_peak_ratio_threshold)
        self._corruption_guard_mode = str(corruption_guard_mode).strip().lower()
        self._voice_eq_enabled = bool(voice_eq_enabled)

        self._backend = PyRNNoise(self._sample_rate_hz)
        self._backend.channels = 1
        self._backend.dtype = np.int16
        self._pending_out = np.zeros((0,), dtype=np.float32)
        self._pending_vad = np.zeros((0,), dtype=np.float32)
        self._pending_ref = np.zeros((0,), dtype=np.float32)
        self._prev_backend_chunk = np.zeros((0,), dtype=np.float32)
        self._last_good_backend_chunk = np.zeros((0,), dtype=np.float32)
        self._last_output_sample = 0.0
        self._declick_prev_output_sample = 0.0
        self._last_inverse_output = np.zeros((0,), dtype=np.float32)

        self._input_highpass_sos = (
            None
            if (not input_highpass_enabled) or input_highpass_cutoff_hz <= 0.0 or input_highpass_cutoff_hz >= 0.5 * self._sample_rate_hz
            else butter(2, input_highpass_cutoff_hz, btype="highpass", fs=float(self._sample_rate_hz), output="sos")
        )
        self._input_highpass_zi = None if self._input_highpass_sos is None else np.zeros((self._input_highpass_sos.shape[0], 2), dtype=np.float32)
        self._output_highpass_sos = (
            None
            if (not output_highpass_enabled) or output_highpass_cutoff_hz <= 0.0 or output_highpass_cutoff_hz >= 0.5 * self._sample_rate_hz
            else butter(2, output_highpass_cutoff_hz, btype="highpass", fs=float(self._sample_rate_hz), output="sos")
        )
        self._output_highpass_zi = None if self._output_highpass_sos is None else np.zeros((self._output_highpass_sos.shape[0], 2), dtype=np.float32)
        self._output_lowpass_sos = (
            None
            if output_lowpass_cutoff_hz <= 0.0 or output_lowpass_cutoff_hz >= 0.5 * self._sample_rate_hz
            else butter(6, output_lowpass_cutoff_hz, btype="lowpass", fs=float(self._sample_rate_hz), output="sos")
        )
        self._output_lowpass_zi = None if self._output_lowpass_sos is None else np.zeros((self._output_lowpass_sos.shape[0], 2), dtype=np.float32)
        if 0.0 < output_notch_freq_hz < 0.5 * self._sample_rate_hz and output_notch_q > 0.0:
            b_notch, a_notch = iirnotch(output_notch_freq_hz, output_notch_q, fs=float(self._sample_rate_hz))
            self._output_notch_sos = tf2sos(b_notch, a_notch)
            self._output_notch_zi = np.zeros((self._output_notch_sos.shape[0], 2), dtype=np.float32)
            self._inverse_notch_zi = np.zeros((self._output_notch_sos.shape[0], 2), dtype=np.float32)
        else:
            self._output_notch_sos = None
            self._output_notch_zi = None
            self._inverse_notch_zi = None
        self._voice_eq_presence_sos = _peaking_eq_sos(
            center_hz=voice_eq_presence_center_hz,
            q=voice_eq_presence_q,
            gain_db=voice_eq_presence_gain_db,
            fs_hz=float(self._sample_rate_hz),
        )
        self._voice_eq_presence_zi = None if self._voice_eq_presence_sos is None else np.zeros((self._voice_eq_presence_sos.shape[0], 2), dtype=np.float32)
        self._voice_eq_lowmid_sos = _peaking_eq_sos(
            center_hz=voice_eq_lowmid_center_hz,
            q=voice_eq_lowmid_q,
            gain_db=voice_eq_lowmid_gain_db,
            fs_hz=float(self._sample_rate_hz),
        )
        self._voice_eq_lowmid_zi = None if self._voice_eq_lowmid_sos is None else np.zeros((self._voice_eq_lowmid_sos.shape[0], 2), dtype=np.float32)
        inverse_band_low_hz = 300.0
        inverse_band_high_hz = 3400.0
        if 0.0 < inverse_band_low_hz < inverse_band_high_hz < 0.5 * self._sample_rate_hz:
            self._inverse_bandstop_sos = butter(
                6,
                [inverse_band_low_hz, inverse_band_high_hz],
                btype="bandstop",
                fs=float(self._sample_rate_hz),
                output="sos",
            )
            self._inverse_bandstop_zi = np.zeros((self._inverse_bandstop_sos.shape[0], 2), dtype=np.float32)
        else:
            self._inverse_bandstop_sos = None
            self._inverse_bandstop_zi = None

        if startup_warmup_enabled:
            silence_i16 = np.zeros((1, self._frame_size), dtype=np.int16)
            for _ in range(max(0, int(startup_warmup_frames))):
                for _vad_prob, den in self._backend.denoise_chunk(silence_i16, partial=False):
                    den_arr = np.asarray(den, dtype=np.float32).reshape(-1)
                    if den_arr.dtype.kind in {"i", "u"} or float(np.max(np.abs(den_arr))) > 1.5:
                        den_arr = den_arr / 32768.0
                    self._prev_backend_chunk = den_arr.astype(np.float32, copy=False)
                    self._last_good_backend_chunk = self._prev_backend_chunk.copy()

    def process(self, frame: np.ndarray) -> DenoiseResult:
        x = np.asarray(frame, dtype=np.float32).reshape(-1)
        x_for_rnnoise = np.asarray(x, dtype=np.float32)
        if self._input_highpass_sos is not None and self._input_highpass_zi is not None and x_for_rnnoise.size > 0:
            x_for_rnnoise, self._input_highpass_zi = sosfilt(self._input_highpass_sos, x_for_rnnoise, zi=self._input_highpass_zi)
            x_for_rnnoise = np.asarray(x_for_rnnoise, dtype=np.float32)
        gain = float(10.0 ** (self._input_gain_db / 20.0))
        x_in = (x_for_rnnoise * gain).astype(np.float32, copy=False)
        expected_output_samples = int(x.shape[0])
        self._pending_ref = np.concatenate([self._pending_ref, x_in], axis=0)
        parts: list[np.ndarray] = []
        vad_parts: list[np.ndarray] = []
        chunk_i16 = np.clip(np.round(x_in * 32768.0), -32768.0, 32767.0).astype(np.int16, copy=False)
        for vad_prob, den in self._backend.denoise_chunk(np.atleast_2d(chunk_i16), partial=False):
            den_arr = np.asarray(den, dtype=np.float32).reshape(-1)
            if den_arr.dtype.kind in {"i", "u"} or float(np.max(np.abs(den_arr))) > 1.5:
                den_arr = den_arr / 32768.0
            den_arr = np.asarray(den_arr, dtype=np.float32)
            if den_arr.size == 0:
                continue
            ref_len = min(int(den_arr.shape[0]), int(self._pending_ref.shape[0]))
            if ref_len > 0:
                ref_chunk = self._pending_ref[:ref_len]
                self._pending_ref = self._pending_ref[ref_len:]
                if ref_len < den_arr.shape[0]:
                    ref_chunk = np.pad(ref_chunk, (0, den_arr.shape[0] - ref_len))
            else:
                ref_chunk = np.zeros((den_arr.shape[0],), dtype=np.float32)
            den_arr = self._guard_backend_output(ref_chunk=ref_chunk, den_arr=den_arr)
            den_arr = self._apply_backend_crossfade(den_arr)
            parts.append(den_arr)
            self._prev_backend_chunk = den_arr.copy()
            self._last_good_backend_chunk = den_arr.copy()
            vad_arr = np.asarray(vad_prob, dtype=np.float32).reshape(-1)
            vad_scalar = float(np.clip(float(vad_arr[0]) if vad_arr.size else 0.0, 0.0, 1.0))
            vad_parts.append(np.full((den_arr.shape[0],), vad_scalar, dtype=np.float32))

        if parts:
            self._pending_out = np.concatenate([self._pending_out, np.concatenate(parts, axis=0)], axis=0)
        if vad_parts:
            self._pending_vad = np.concatenate([self._pending_vad, np.concatenate(vad_parts, axis=0)], axis=0)

        if self._pending_out.shape[0] < expected_output_samples:
            shortfall = expected_output_samples - self._pending_out.shape[0]
            out = np.pad(self._pending_out, (0, shortfall), constant_values=float(self._last_output_sample))
            self._pending_out = np.zeros((0,), dtype=np.float32)
        else:
            out = self._pending_out[:expected_output_samples]
            self._pending_out = self._pending_out[expected_output_samples:]
        if self._pending_vad.shape[0] < expected_output_samples:
            vad_env = np.pad(self._pending_vad, (0, expected_output_samples - self._pending_vad.shape[0]), constant_values=0.0)
            self._pending_vad = np.zeros((0,), dtype=np.float32)
        else:
            vad_env = self._pending_vad[:expected_output_samples]
            self._pending_vad = self._pending_vad[expected_output_samples:]

        if out.size > 0:
            self._last_output_sample = float(out[-1])
        mixed = self._mix_output(x=x, denoised=np.asarray(out, dtype=np.float32), vad_env=np.asarray(vad_env, dtype=np.float32))
        mixed = self._apply_output_filters(np.asarray(mixed, dtype=np.float32))

        inverse = np.asarray(x - mixed, dtype=np.float32)
        if self._inverse_bandstop_sos is not None and self._inverse_bandstop_zi is not None and inverse.size > 0:
            inverse, self._inverse_bandstop_zi = sosfilt(self._inverse_bandstop_sos, inverse, zi=self._inverse_bandstop_zi)
            inverse = np.asarray(inverse, dtype=np.float32)
        if self._output_notch_sos is not None and self._inverse_notch_zi is not None and inverse.size > 0:
            inverse, self._inverse_notch_zi = sosfilt(self._output_notch_sos, inverse, zi=self._inverse_notch_zi)
            inverse = np.asarray(inverse, dtype=np.float32)
        self._last_inverse_output = inverse.copy()
        return DenoiseResult(denoised=np.asarray(mixed, dtype=np.float32), residual=inverse)

    def get_last_inverse_output(self) -> np.ndarray:
        return np.asarray(self._last_inverse_output, dtype=np.float32).copy()

    def _guard_backend_output(self, *, ref_chunk: np.ndarray, den_arr: np.ndarray) -> np.ndarray:
        if not self._corruption_guard_enabled:
            return den_arr
        in_peak = float(np.max(np.abs(ref_chunk))) if ref_chunk.size else 0.0
        out_peak = float(np.max(np.abs(den_arr))) if den_arr.size else 0.0
        in_rms = float(np.sqrt(np.mean(np.asarray(ref_chunk, dtype=np.float64) ** 2) + 1e-12))
        out_rms = float(np.sqrt(np.mean(np.asarray(den_arr, dtype=np.float64) ** 2) + 1e-12))
        bad_rms = out_rms > (self._corruption_guard_rms_ratio_threshold * max(in_rms, 1e-6))
        bad_peak = out_peak > (self._corruption_guard_peak_ratio_threshold * max(in_peak, 1e-6))
        if not (bad_rms or bad_peak):
            return den_arr
        if self._corruption_guard_mode == "use_input":
            return np.asarray(ref_chunk, dtype=np.float32).copy()
        if self._corruption_guard_mode == "mute":
            return np.zeros_like(den_arr)
        if self._last_good_backend_chunk.shape == den_arr.shape and self._last_good_backend_chunk.size:
            return self._last_good_backend_chunk.copy()
        return np.asarray(ref_chunk, dtype=np.float32).copy()

    def _apply_backend_crossfade(self, chunk: np.ndarray) -> np.ndarray:
        out_chunk = np.asarray(chunk, dtype=np.float32).reshape(-1).copy()
        if (not self._chunk_crossfade_enabled) or self._prev_backend_chunk.size == 0:
            return out_chunk
        fade_len = min(self._chunk_crossfade_samples, out_chunk.shape[0] // 4, self._prev_backend_chunk.shape[0], out_chunk.shape[0])
        if fade_len <= 0:
            return out_chunk
        fade_out = np.linspace(1.0, 0.0, fade_len, endpoint=True, dtype=np.float32)
        fade_in = np.linspace(0.0, 1.0, fade_len, endpoint=True, dtype=np.float32)
        out_chunk[:fade_len] = (self._prev_backend_chunk[-fade_len:] * fade_out) + (out_chunk[:fade_len] * fade_in)
        return out_chunk

    def _mix_output(self, *, x: np.ndarray, denoised: np.ndarray, vad_env: np.ndarray) -> np.ndarray:
        if self._vad_adaptive_blend_enabled:
            speech_preserve = np.clip(np.power(np.clip(vad_env, 0.0, 1.0), self._vad_blend_gamma), self._vad_min_speech_preserve, self._vad_max_speech_preserve).astype(np.float32, copy=False)
            effective_preserve = np.clip(speech_preserve + (1.0 - self._wet_mix), 0.0, 1.0).astype(np.float32, copy=False)
        else:
            effective_preserve = np.full((x.shape[0],), 1.0 - self._wet_mix, dtype=np.float32)
        mixed = ((effective_preserve * x) + ((1.0 - effective_preserve) * denoised)).astype(np.float32, copy=False)
        return self._apply_declick(mixed)

    def _apply_declick(self, mixed: np.ndarray) -> np.ndarray:
        if not self._declick_enabled:
            if mixed.size > 0:
                self._declick_prev_output_sample = float(mixed[-1])
            return np.asarray(mixed, dtype=np.float32)
        out = np.asarray(mixed, dtype=np.float32).copy()
        prev = float(self._declick_prev_output_sample)
        for idx in range(out.shape[0]):
            cur = float(out[idx])
            if self._declick_conditional and abs(cur - prev) <= self._declick_spike_threshold:
                prev = cur
                continue
            smoothed = float((self._declick_alpha * prev) + ((1.0 - self._declick_alpha) * cur))
            out[idx] = smoothed
            prev = smoothed
        self._declick_prev_output_sample = prev
        return out

    def _apply_output_filters(self, mixed: np.ndarray) -> np.ndarray:
        out = np.asarray(mixed, dtype=np.float32)
        if self._output_highpass_sos is not None and self._output_highpass_zi is not None and out.size > 0:
            out, self._output_highpass_zi = sosfilt(self._output_highpass_sos, out, zi=self._output_highpass_zi)
            out = np.asarray(out, dtype=np.float32)
        if self._output_lowpass_sos is not None and self._output_lowpass_zi is not None and out.size > 0:
            out, self._output_lowpass_zi = sosfilt(self._output_lowpass_sos, out, zi=self._output_lowpass_zi)
            out = np.asarray(out, dtype=np.float32)
        if self._output_notch_sos is not None and self._output_notch_zi is not None and out.size > 0:
            out, self._output_notch_zi = sosfilt(self._output_notch_sos, out, zi=self._output_notch_zi)
            out = np.asarray(out, dtype=np.float32)
        if self._voice_eq_enabled and out.size > 0:
            if self._voice_eq_lowmid_sos is not None and self._voice_eq_lowmid_zi is not None:
                out, self._voice_eq_lowmid_zi = sosfilt(self._voice_eq_lowmid_sos, out, zi=self._voice_eq_lowmid_zi)
                out = np.asarray(out, dtype=np.float32)
            if self._voice_eq_presence_sos is not None and self._voice_eq_presence_zi is not None:
                out, self._voice_eq_presence_zi = sosfilt(self._voice_eq_presence_sos, out, zi=self._voice_eq_presence_zi)
                out = np.asarray(out, dtype=np.float32)
        if self._output_clip_guard_enabled and out.size > 0:
            out = np.clip(out, -self._output_clip_guard_abs_max, self._output_clip_guard_abs_max).astype(np.float32, copy=False)
        return out
