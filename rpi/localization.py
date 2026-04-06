from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import scipy.signal as signal
from scipy.linalg import cho_factor, cho_solve


def _wrap_degrees(angle_deg: float) -> float:
    return float(angle_deg % 360.0)


def _circular_local_maxima(
    values: np.ndarray,
    *,
    min_separation_bins: int,
    max_peaks: int,
) -> list[int]:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size == 0:
        return []
    peaks: list[tuple[float, int]] = []
    for idx in range(arr.size):
        prev_v = float(arr[(idx - 1) % arr.size])
        cur_v = float(arr[idx])
        next_v = float(arr[(idx + 1) % arr.size])
        if cur_v > prev_v and cur_v >= next_v:
            peaks.append((cur_v, int(idx)))
    peaks.sort(key=lambda item: item[0], reverse=True)
    picked: list[int] = []
    for _score, idx in peaks:
        if any(min(abs(idx - prev), arr.size - abs(idx - prev)) < min_separation_bins for prev in picked):
            continue
        picked.append(int(idx))
        if len(picked) >= max_peaks:
            break
    return picked


def _gcc_phat(
    x: np.ndarray,
    y: np.ndarray,
    *,
    sample_rate_hz: int,
    max_tau_s: float,
    bandlimit_hz: float = 3500.0,
) -> tuple[np.ndarray, np.ndarray]:
    x_arr = np.asarray(x, dtype=np.float64).reshape(-1)
    y_arr = np.asarray(y, dtype=np.float64).reshape(-1)
    if x_arr.shape[0] != y_arr.shape[0]:
        raise ValueError("gcc_phat inputs must have the same length")
    if x_arr.size == 0:
        return np.zeros((0,), dtype=np.float64), np.zeros((0,), dtype=np.int64)
    x_arr = x_arr - float(np.mean(x_arr))
    y_arr = y_arr - float(np.mean(y_arr))

    fft_size = int(x_arr.shape[0] + y_arr.shape[0])
    x_fft = np.fft.rfft(x_arr, n=fft_size)
    y_fft = np.fft.rfft(y_arr, n=fft_size)
    cross_power = x_fft * np.conj(y_fft)
    freqs_hz = np.fft.rfftfreq(fft_size, d=1.0 / float(sample_rate_hz))
    cross_power[freqs_hz < 50.0] = 0.0
    cross_power /= np.maximum(np.abs(cross_power), 1e-8)
    corr = np.fft.irfft(cross_power, n=fft_size)
    corr = np.fft.fftshift(corr)

    center = fft_size // 2
    max_lag = int(np.ceil(float(max_tau_s) * float(sample_rate_hz)))
    start = max(0, center - max_lag)
    stop = min(corr.shape[0], center + max_lag + 1)
    lags = np.arange(start - center, stop - center, dtype=np.int64)
    return np.asarray(corr[start:stop], dtype=np.float64), lags


@dataclass(slots=True)
class LocalizationResult:
    doa_deg: float | None
    confidence: float
    accepted: bool
    held: bool
    spectrum: np.ndarray


class SRPPHATLocalizer:
    def __init__(
        self,
        *,
        mic_positions_xyz: np.ndarray,
        sample_rate_hz: int = 16000,
        grid_size: int = 72,
        spectrum_ema_alpha: float = 0.9,
        peak_min_sharpness: float = 0.12,
        peak_min_margin: float = 0.04,
        hold_frames: int = 2,
        bandlimit_hz: float = 3500.0,
        **_: object,
    ) -> None:
        mic_positions = np.asarray(mic_positions_xyz, dtype=np.float64)
        if mic_positions.ndim != 2:
            raise ValueError("mic_positions_xyz must be a 2D array")
        if mic_positions.shape[1] == 3:
            mic_positions = mic_positions.T
        if mic_positions.shape[0] != 3:
            raise ValueError("mic_positions_xyz must have shape (n_mics, 3) or (3, n_mics)")

        self._mic_positions_xyz = np.asarray(mic_positions.T, dtype=np.float64)
        self._sample_rate_hz = int(sample_rate_hz)
        self._grid_size = max(1, int(grid_size))
        self._spectrum_ema_alpha = float(np.clip(spectrum_ema_alpha, 0.0, 1.0))
        self._peak_min_sharpness = float(max(0.0, peak_min_sharpness))
        self._peak_min_margin = float(max(0.0, peak_min_margin))
        self._hold_frames = max(0, int(hold_frames))
        self._bandlimit_hz = float(max(200.0, bandlimit_hz))
        self._sound_speed_m_s = 343.0

        self._pairs = list(combinations(range(int(self._mic_positions_xyz.shape[0])), 2))
        self._angles_deg = np.linspace(0.0, 360.0, self._grid_size, endpoint=False, dtype=np.float64)
        self._angles_rad = np.deg2rad(self._angles_deg)
        self._directions = np.stack(
            [np.cos(self._angles_rad), np.sin(self._angles_rad), np.zeros_like(self._angles_rad)],
            axis=1,
        )
        self._max_pair_delay_s = {
            pair: float(np.linalg.norm(self._mic_positions_xyz[pair[0]] - self._mic_positions_xyz[pair[1]]) / self._sound_speed_m_s)
            for pair in self._pairs
        }
        self._expected_lag_samples = {
            pair: np.asarray(
                ((self._mic_positions_xyz[pair[0]] - self._mic_positions_xyz[pair[1]]) @ self._directions.T)
                / self._sound_speed_m_s
                * float(self._sample_rate_hz),
                dtype=np.float64,
            )
            for pair in self._pairs
        }
        self._spectrum_ema: np.ndarray | None = None
        self._last_accepted_doa_deg: float | None = None
        self._last_confidence = 0.0
        self._hold_remaining = 0

    def process(self, audio_window: np.ndarray) -> LocalizationResult:
        audio = np.asarray(audio_window, dtype=np.float32)
        if audio.ndim != 2:
            raise ValueError("audio_window must be shape (samples, n_mics)")
        if audio.shape[1] != int(self._mic_positions_xyz.shape[0]):
            raise ValueError("audio_window mic count does not match mic geometry")
        if audio.shape[0] == 0:
            return self._held_or_empty(np.zeros((self._grid_size,), dtype=np.float64))

        spectrum = np.zeros((self._grid_size,), dtype=np.float64)
        valid_pairs = 0
        for pair in self._pairs:
            corr, lags = _gcc_phat(
                audio[:, pair[0]],
                audio[:, pair[1]],
                sample_rate_hz=self._sample_rate_hz,
                max_tau_s=self._max_pair_delay_s[pair],
                bandlimit_hz=self._bandlimit_hz,
            )
            if corr.size == 0:
                continue
            valid_pairs += 1
            spectrum += np.interp(
                self._expected_lag_samples[pair],
                lags.astype(np.float64, copy=False),
                corr,
                left=0.0,
                right=0.0,
            )

        if valid_pairs <= 0:
            return self._held_or_empty(np.zeros((self._grid_size,), dtype=np.float64))

        if self._spectrum_ema is None or self._spectrum_ema.shape != spectrum.shape:
            smooth_spectrum = np.asarray(spectrum, dtype=np.float64)
        else:
            smooth_spectrum = (
                self._spectrum_ema_alpha * self._spectrum_ema
                + (1.0 - self._spectrum_ema_alpha) * np.asarray(spectrum, dtype=np.float64)
            )
        self._spectrum_ema = np.asarray(smooth_spectrum, dtype=np.float64)

        best_idx = int(np.argmax(smooth_spectrum))
        best_power = float(smooth_spectrum[best_idx])
        median_power = float(np.median(smooth_spectrum))
        mean_power = float(np.mean(smooth_spectrum))
        spread = float(max(np.std(smooth_spectrum), 1e-8))
        margin = float(best_power - median_power)
        confidence = float(max(0.0, margin) / (abs(mean_power) + spread + 1e-8))
        accepted = bool((best_power > median_power + self._peak_min_margin) and (margin / spread >= self._peak_min_sharpness))

        if accepted:
            doa_deg = _wrap_degrees(float(self._angles_deg[best_idx]))
            self._last_accepted_doa_deg = doa_deg
            self._last_confidence = confidence
            self._hold_remaining = self._hold_frames
            return LocalizationResult(doa_deg=doa_deg, confidence=confidence, accepted=True, held=False, spectrum=np.asarray(smooth_spectrum, dtype=np.float64))
        return self._held_or_empty(smooth_spectrum)

    def _held_or_empty(self, spectrum: np.ndarray) -> LocalizationResult:
        if self._last_accepted_doa_deg is not None and self._hold_remaining > 0:
            self._hold_remaining -= 1
            return LocalizationResult(
                doa_deg=float(self._last_accepted_doa_deg),
                confidence=float(self._last_confidence),
                accepted=False,
                held=True,
                spectrum=np.asarray(spectrum, dtype=np.float64),
            )
        return LocalizationResult(doa_deg=None, confidence=0.0, accepted=False, held=False, spectrum=np.asarray(spectrum, dtype=np.float64))


class CaponLocalization:
    def __init__(
        self,
        mic_pos=None,
        fs: int = 16000,
        nfft: int = 512,
        overlap: float = 0.5,
        freq_range: tuple[int, int] = (500, 3500),
        max_sources: int = 1,
        *,
        mic_positions_xyz: np.ndarray | None = None,
        sample_rate_hz: int | None = None,
        **kwargs,
    ) -> None:
        if mic_pos is None:
            if mic_positions_xyz is None:
                raise ValueError("mic_pos or mic_positions_xyz is required")
            mic_pos = mic_positions_xyz
        if sample_rate_hz is not None:
            fs = int(sample_rate_hz)

        self.mic_pos = np.asarray(mic_pos, dtype=np.float64)
        self.fs = int(fs)
        self.nfft = int(nfft)
        self.overlap = float(overlap)
        self.freq_range = tuple(int(v) for v in freq_range)
        self.max_sources = int(max_sources)
        self.c = 343.0

        if self.mic_pos.ndim != 2:
            raise ValueError("mic_pos must be a 2D array")
        if self.mic_pos.shape[1] == 3:
            self.mic_pos = self.mic_pos.T
        if self.mic_pos.shape[0] != 3:
            raise ValueError("mic_pos must have shape (3, M) or (M, 3)")

        self.grid_size = int(kwargs.get("grid_size", 360))
        self.min_separation_deg = float(kwargs.get("min_separation_deg", 15.0))
        self.diagonal_loading = float(kwargs.get("diagonal_loading", 1e-3))

        self.vad_enabled = bool(kwargs.get("vad_enabled", True))
        self.vad_frame_ms = int(kwargs.get("vad_frame_ms", 20))
        self.vad_aggressiveness = int(kwargs.get("vad_aggressiveness", 2))
        self.vad_min_speech_ratio = float(kwargs.get("vad_min_speech_ratio", 0.2))

        self.spectrum_ema_alpha = float(kwargs.get("capon_spectrum_ema_alpha", kwargs.get("spectrum_ema_alpha", 0.78)))
        self.peak_min_sharpness = float(kwargs.get("capon_peak_min_sharpness", kwargs.get("peak_min_sharpness", 0.12)))
        self.peak_min_margin = float(kwargs.get("capon_peak_min_margin", kwargs.get("peak_min_margin", 0.04)))
        self.hold_frames = int(kwargs.get("capon_hold_frames", kwargs.get("hold_frames", 2)))
        self.freq_bin_subsample_stride = int(max(1, kwargs.get("capon_freq_bin_subsample_stride", kwargs.get("freq_bin_subsample_stride", 1))))
        self.freq_bin_min_hz = kwargs.get("capon_freq_bin_min_hz", None)
        self.freq_bin_max_hz = kwargs.get("capon_freq_bin_max_hz", None)
        self.use_cholesky_solve = bool(kwargs.get("capon_use_cholesky_solve", kwargs.get("use_cholesky_solve", False)))
        self.covariance_ema_alpha = float(np.clip(kwargs.get("capon_covariance_ema_alpha", kwargs.get("covariance_ema_alpha", 0.0)), 0.0, 0.999))
        self.full_scan_every_n_updates = int(max(1, kwargs.get("capon_full_scan_every_n_updates", kwargs.get("full_scan_every_n_updates", 1))))
        self.local_refine_enabled = bool(kwargs.get("capon_local_refine_enabled", kwargs.get("local_refine_enabled", False)))
        self.local_refine_half_width_deg = float(max(1.0, kwargs.get("capon_local_refine_half_width_deg", kwargs.get("local_refine_half_width_deg", 30.0))))
        self.refine_window_deg = float(kwargs.get("capon_refine_window_deg", 20.0))
        self.refine_step_deg = float(kwargs.get("capon_refine_step_deg", 2.0))

        self._spectrum_accum: np.ndarray | None = None
        self._covariance_accum: np.ndarray | None = None
        self._covariance_freqs_hz: np.ndarray | None = None
        self._last_accepted_angle: float | None = None
        self._last_accepted_score: float = 0.0
        self._hold_remaining: int = 0
        self._update_counter: int = 0
        self.last_debug: dict[str, object] = {}
        self.last_peak_scores: list[float] = []

    def _speech_active(self, audio: np.ndarray) -> bool:
        if not self.vad_enabled:
            return True
        mono = np.asarray(audio, dtype=np.float32)
        if mono.ndim == 2:
            mono = mono[:, 0]
        mono = np.asarray(mono, dtype=np.float32).reshape(-1)
        try:
            import webrtcvad
        except ModuleNotFoundError:
            return True
        valid_rates = (8000, 16000, 32000, 48000)
        target_fs = min(valid_rates, key=lambda r: abs(r - self.fs))
        frame_ms = 20 if self.vad_frame_ms not in {10, 20, 30} else self.vad_frame_ms
        mono_rs = mono
        if self.fs != target_fs:
            gcd = np.gcd(self.fs, target_fs)
            mono_rs = signal.resample_poly(mono, target_fs // gcd, self.fs // gcd).astype(np.float32)
        frame_len = int(target_fs * frame_ms / 1000)
        if frame_len <= 0 or mono_rs.size < frame_len:
            return False
        vad = webrtcvad.Vad(int(np.clip(self.vad_aggressiveness, 0, 3)))
        peak = float(np.max(np.abs(mono_rs)))
        if peak > 1e-6:
            mono_rs = mono_rs / peak
        pcm16 = np.round(np.clip(mono_rs, -1.0, 1.0) * 32767.0).astype(np.int16)
        total = 0
        voiced = 0
        for start in range(0, pcm16.size - frame_len + 1, frame_len):
            total += 1
            if vad.is_speech(pcm16[start : start + frame_len].tobytes(), target_fs):
                voiced += 1
        return total > 0 and (voiced / total) >= self.vad_min_speech_ratio

    def _compute_stft_roi(self, audio: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
        noverlap = min(int(round(self.nfft * self.overlap)), self.nfft - 1)
        f_vec, _t, zxx = signal.stft(audio, fs=self.fs, nperseg=self.nfft, noverlap=noverlap, boundary=None, padded=False)
        f_min, f_max = self.freq_range
        if self.freq_bin_min_hz is not None:
            f_min = max(f_min, int(self.freq_bin_min_hz))
        if self.freq_bin_max_hz is not None:
            f_max = min(f_max, int(self.freq_bin_max_hz))
        eligible = np.flatnonzero((f_vec >= f_min) & (f_vec <= f_max))
        if eligible.size == 0:
            return None
        eligible = eligible[:: self.freq_bin_subsample_stride]
        zxx_roi = zxx[:, eligible, :]
        if zxx_roi.shape[1] == 0 or zxx_roi.shape[2] == 0:
            return None
        return np.asarray(f_vec[eligible], dtype=np.float64), np.asarray(zxx_roi, dtype=np.complex128)

    def _search_angles_for_update(self) -> tuple[np.ndarray, bool]:
        self._update_counter += 1
        full_scan = (
            not self.local_refine_enabled
            or self._last_accepted_angle is None
            or self.full_scan_every_n_updates <= 1
            or (self._update_counter - 1) % self.full_scan_every_n_updates == 0
        )
        if full_scan:
            return np.linspace(0.0, 2.0 * np.pi, self.grid_size, endpoint=False, dtype=np.float64), True
        step_deg = max(360.0 / max(self.grid_size, 1), 0.5)
        offsets = np.arange(
            -self.local_refine_half_width_deg,
            self.local_refine_half_width_deg + 0.5 * step_deg,
            step_deg,
            dtype=np.float64,
        )
        center_deg = float(np.degrees(self._last_accepted_angle) % 360.0)
        return np.deg2rad((center_deg + offsets) % 360.0), False

    def _update_covariance_bank(self, relevant_freqs: np.ndarray, zxx_roi: np.ndarray) -> np.ndarray:
        m = int(zxx_roi.shape[0])
        nf = int(zxx_roi.shape[1])
        if (
            self._covariance_accum is None
            or self._covariance_accum.shape != (nf, m, m)
            or self._covariance_freqs_hz is None
            or not np.allclose(self._covariance_freqs_hz, relevant_freqs)
        ):
            self._covariance_accum = np.zeros((nf, m, m), dtype=np.complex128)
            self._covariance_freqs_hz = relevant_freqs.copy()
        out = np.zeros_like(self._covariance_accum)
        use_ema = self.covariance_ema_alpha > 0.0
        for fi in range(nf):
            snaps = np.asarray(zxx_roi[:, fi, :], dtype=np.complex128)
            if snaps.shape[1] == 0:
                continue
            cov_inst = (snaps @ snaps.conj().T) / max(1, snaps.shape[1])
            if use_ema:
                cov = self.covariance_ema_alpha * self._covariance_accum[fi] + (1.0 - self.covariance_ema_alpha) * cov_inst
            else:
                cov = cov_inst
            self._covariance_accum[fi] = cov
            out[fi] = cov
        return out

    def _capon_spectrum_from_roi(self, relevant_freqs: np.ndarray, zxx_roi: np.ndarray, search_angles: np.ndarray) -> np.ndarray:
        m = int(zxx_roi.shape[0])
        dirs = np.stack([np.cos(search_angles), np.sin(search_angles), np.zeros_like(search_angles)], axis=1)
        spectrum = np.zeros(search_angles.shape[0], dtype=np.float64)
        eye = np.eye(m, dtype=np.complex128)
        covariances = self._update_covariance_bank(relevant_freqs, zxx_roi)

        for fi, freq_hz in enumerate(relevant_freqs):
            cov = covariances[fi]
            if not np.any(cov):
                continue
            trace_scale = float(np.real(np.trace(cov))) / max(1, m)
            load = max(self.diagonal_loading * max(trace_scale, 1e-8), 1e-8)
            cov_loaded = cov + (load * eye)

            tau = (self.mic_pos.T @ dirs.T) / self.c
            tau -= np.mean(tau, axis=0, keepdims=True)
            steering = np.exp(-1j * 2.0 * np.pi * float(freq_hz) * tau)

            solved = None
            if self.use_cholesky_solve:
                try:
                    chol = cho_factor(cov_loaded, lower=False, check_finite=False)
                    solved = cho_solve(chol, steering, check_finite=False)
                except Exception:
                    solved = None
            if solved is None:
                try:
                    solved = np.linalg.solve(cov_loaded, steering)
                except np.linalg.LinAlgError:
                    solved = np.linalg.pinv(cov_loaded) @ steering

            denom = np.maximum(np.real(np.einsum("ma,ma->a", steering.conj(), solved, optimize=True)), 1e-10)
            spectrum += 1.0 / denom

        spectrum = np.where(np.isfinite(spectrum), spectrum, 0.0)
        spectrum = np.clip(spectrum, 0.0, None)
        vmax = float(np.max(spectrum))
        if vmax > 0.0:
            spectrum /= vmax
        return spectrum

    def _smooth_spectrum(self, spectrum: np.ndarray) -> np.ndarray:
        if self._spectrum_accum is None or self._spectrum_accum.shape != spectrum.shape:
            self._spectrum_accum = np.asarray(spectrum, dtype=np.float64)
        else:
            alpha = float(np.clip(self.spectrum_ema_alpha, 0.0, 0.98))
            self._spectrum_accum = alpha * self._spectrum_accum + (1.0 - alpha) * spectrum
        s = np.asarray(self._spectrum_accum, dtype=np.float64)
        if np.max(s) > 0.0:
            s = s / np.max(s)
        return s

    def _score_peak_at_index(self, spectrum: np.ndarray, peak_idx: int, *, exclusion_deg: float = 12.0) -> dict[str, float | int | bool | None]:
        s = np.asarray(spectrum, dtype=np.float64)
        idx = int(peak_idx % max(1, s.size))
        best = float(s[idx])
        left = float(s[(idx - 1) % s.size])
        right = float(s[(idx + 1) % s.size])
        global_baseline = float(np.median(s))
        local_contrast = float(max(0.0, best - max(left, right)))
        peak_sharpness = float(max(0.0, best - global_baseline))
        exclusion = max(2, int(round(exclusion_deg / (360.0 / max(s.size, 1)))))
        second_score = 0.0
        second_idx = None
        for si, sv in sorted(enumerate(s.tolist()), key=lambda x: x[1], reverse=True):
            if abs(si - idx) <= exclusion or (s.size - abs(si - idx)) <= exclusion:
                continue
            second_idx = int(si)
            second_score = float(sv)
            break
        peak_margin = float(max(0.0, best - second_score))
        confidence = float(np.clip(0.5 * best + 0.25 * peak_sharpness + 0.25 * peak_margin, 0.0, 1.0))
        accepted = bool(peak_sharpness >= self.peak_min_sharpness and peak_margin >= self.peak_min_margin)
        return {
            "best_idx": idx,
            "best_score": best,
            "second_idx": second_idx,
            "local_contrast": local_contrast,
            "peak_sharpness": peak_sharpness,
            "peak_margin": peak_margin,
            "confidence": confidence,
            "accepted": accepted,
        }

    def _score_peak(self, spectrum: np.ndarray, *, exclusion_deg: float = 12.0) -> dict[str, float | int | bool | None]:
        return self._score_peak_at_index(spectrum, int(np.argmax(spectrum)), exclusion_deg=exclusion_deg)

    def _held_result(self, spectrum: np.ndarray) -> tuple[list[float], np.ndarray, list[float]]:
        if self._last_accepted_angle is not None and self._hold_remaining > 0:
            self._hold_remaining -= 1
            held_score = float(max(0.0, self._last_accepted_score * 0.9))
            self.last_peak_scores = [held_score]
            self.last_debug["output_mode"] = "held"
            return [float(self._last_accepted_angle)], np.asarray(spectrum, dtype=np.float64), []
        self.last_peak_scores = []
        self.last_debug["output_mode"] = "abstained"
        return [], np.asarray(spectrum, dtype=np.float64), []

    def estimate(self, audio: np.ndarray) -> tuple[list[float], np.ndarray, list[float]]:
        audio_arr = np.asarray(audio, dtype=np.float32)
        if audio_arr.ndim != 2:
            raise ValueError("audio must be shape (samples, n_mics) or (n_mics, samples)")
        if audio_arr.shape[0] != self.mic_pos.shape[1] and audio_arr.shape[1] == self.mic_pos.shape[1]:
            audio_arr = audio_arr.T
        if audio_arr.shape[0] != self.mic_pos.shape[1]:
            raise ValueError("audio mic count does not match mic geometry")

        speech_active = self._speech_active(audio_arr)
        self.last_debug = {"vad_enabled": self.vad_enabled, "window_speech_active": speech_active}
        if not speech_active:
            self._spectrum_accum = None
            return self._held_result(np.zeros(self.grid_size, dtype=np.float64))

        roi = self._compute_stft_roi(audio_arr)
        if roi is None:
            return [], np.zeros(self.grid_size, dtype=np.float64), []
        relevant_freqs, zxx_roi = roi

        search_angles, used_full_scan = self._search_angles_for_update()
        spectrum = self._capon_spectrum_from_roi(relevant_freqs, zxx_roi, search_angles)
        smooth = self._smooth_spectrum(spectrum)
        if smooth.size == 0:
            return [], smooth, []

        peak = self._score_peak(smooth)
        self.last_debug.update(
            {
                "used_full_scan": used_full_scan,
                "peak_index": peak["best_idx"],
                "peak_score": peak["best_score"],
                "peak_sharpness": peak["peak_sharpness"],
                "peak_margin": peak["peak_margin"],
                "confidence": peak["confidence"],
            }
        )

        if bool(peak["accepted"]):
            doa = float(search_angles[int(peak["best_idx"])])
            self._last_accepted_angle = doa
            self._last_accepted_score = float(peak["confidence"])
            self._hold_remaining = self.hold_frames
            self.last_debug["output_mode"] = "accepted"
            self.last_peak_scores = [float(peak["confidence"])]
            return [doa], smooth, []

        return self._held_result(smooth)

    def process(self, audio_window: np.ndarray) -> LocalizationResult:
        doas_rad, spectrum, _ = self.estimate(audio_window)
        if doas_rad:
            confidence = float(self.last_peak_scores[0]) if self.last_peak_scores else float(self._last_accepted_score)
            output_mode = str(self.last_debug.get("output_mode", "accepted"))
            return LocalizationResult(
                doa_deg=_wrap_degrees(float(np.degrees(doas_rad[0]))),
                confidence=confidence,
                accepted=output_mode == "accepted",
                held=output_mode == "held",
                spectrum=np.asarray(spectrum, dtype=np.float64),
            )
        return LocalizationResult(doa_deg=None, confidence=0.0, accepted=False, held=False, spectrum=np.asarray(spectrum, dtype=np.float64))
