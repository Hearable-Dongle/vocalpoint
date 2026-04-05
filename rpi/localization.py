from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal
from scipy.linalg import cho_factor, cho_solve


def _circular_local_maxima(
    values: np.ndarray,
    *,
    min_separation_bins: int,
    max_peaks: int,
) -> list[int]:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size == 0:
        return []
    candidates: list[tuple[float, int]] = []
    for idx in range(arr.size):
        prev_v = arr[(idx - 1) % arr.size]
        cur_v = arr[idx]
        next_v = arr[(idx + 1) % arr.size]
        if cur_v > prev_v and cur_v >= next_v:
            candidates.append((float(cur_v), int(idx)))
    candidates.sort(key=lambda item: item[0], reverse=True)

    chosen: list[int] = []
    for _score, idx in candidates:
        if any(min(abs(idx - other), arr.size - abs(idx - other)) < min_separation_bins for other in chosen):
            continue
        chosen.append(int(idx))
        if len(chosen) >= max(1, int(max_peaks)):
            break
    return chosen


@dataclass(slots=True)
class LocalizationResult:
    doa_deg: float | None
    confidence: float
    accepted: bool
    held: bool
    spectrum: np.ndarray


class CaponLocalizer:
    def __init__(
        self,
        *,
        mic_positions_xyz: np.ndarray,
        sample_rate_hz: int = 16000,
        nfft: int = 512,
        overlap: float = 0.5,
        freq_range_hz: tuple[int, int] = (200, 3000),
        grid_size: int = 72,
        diagonal_loading: float = 1e-3,
        spectrum_ema_alpha: float = 0.78,
        peak_min_sharpness: float = 0.12,
        peak_min_margin: float = 0.04,
        hold_frames: int = 2,
        freq_bin_subsample_stride: int = 1,
        use_cholesky_solve: bool = False,
        covariance_ema_alpha: float = 0.0,
        full_scan_every_n_updates: int = 1,
        local_refine_enabled: bool = False,
        local_refine_half_width_deg: float = 30.0,
    ) -> None:
        self._mic_positions_xyz = np.asarray(mic_positions_xyz, dtype=np.float64)
        if self._mic_positions_xyz.ndim != 2:
            raise ValueError("mic_positions_xyz must be a 2D array")
        if self._mic_positions_xyz.shape[1] == 3:
            self._mic_positions_xyz = self._mic_positions_xyz.T
        if self._mic_positions_xyz.shape[0] != 3:
            raise ValueError("mic_positions_xyz must have shape (n_mics, 3) or (3, n_mics)")

        self._mic_pos_xy = np.asarray(self._mic_positions_xyz[:2, :], dtype=np.float64)
        self._sample_rate_hz = int(sample_rate_hz)
        self._nfft = int(nfft)
        self._overlap = float(overlap)
        self._freq_range_hz = (int(freq_range_hz[0]), int(freq_range_hz[1]))
        self._grid_size = int(grid_size)
        self._diagonal_loading = float(diagonal_loading)
        self._spectrum_ema_alpha = float(spectrum_ema_alpha)
        self._peak_min_sharpness = float(peak_min_sharpness)
        self._peak_min_margin = float(peak_min_margin)
        self._hold_frames = int(hold_frames)
        self._freq_bin_subsample_stride = max(1, int(freq_bin_subsample_stride))
        self._use_cholesky_solve = bool(use_cholesky_solve)
        self._covariance_ema_alpha = float(np.clip(covariance_ema_alpha, 0.0, 0.999))
        self._full_scan_every_n_updates = max(1, int(full_scan_every_n_updates))
        self._local_refine_enabled = bool(local_refine_enabled)
        self._local_refine_half_width_deg = float(max(1.0, local_refine_half_width_deg))
        self._sound_speed_m_s = 343.0

        self._spectrum_accum: np.ndarray | None = None
        self._covariance_accum: np.ndarray | None = None
        self._covariance_freqs_hz: np.ndarray | None = None
        self._last_accepted_angle_rad: float | None = None
        self._last_accepted_score: float = 0.0
        self._hold_remaining = 0
        self._update_counter = 0

    def process(self, audio_window: np.ndarray) -> LocalizationResult:
        audio = np.asarray(audio_window, dtype=np.float32)
        if audio.ndim != 2:
            raise ValueError("audio_window must be shape (samples, n_mics)")
        if audio.shape[1] != int(self._mic_pos_xy.shape[1]):
            raise ValueError("audio_window mic count does not match mic geometry")

        roi = self._compute_stft_roi(audio.T)
        if roi is None:
            return self._held_or_empty(np.zeros((self._grid_size,), dtype=np.float64))
        relevant_freqs, zxx_roi = roi

        search_angles_rad, used_full_scan = self._search_angles_for_update()
        spectrum = self._capon_spectrum_from_roi(relevant_freqs, zxx_roi, search_angles_rad)
        smooth_spectrum = self._smooth_spectrum(spectrum)
        if smooth_spectrum.size == 0:
            return self._held_or_empty(smooth_spectrum)

        peak_eval = self._score_peak(smooth_spectrum)
        best_idx = int(peak_eval["best_idx"])
        confidence = float(peak_eval["confidence"])
        accepted = bool(peak_eval["accepted"])
        _ = used_full_scan

        if accepted:
            self._last_accepted_angle_rad = float(search_angles_rad[best_idx])
            self._last_accepted_score = confidence
            self._hold_remaining = max(0, self._hold_frames)
            return LocalizationResult(
                doa_deg=float(np.degrees(search_angles_rad[best_idx]) % 360.0),
                confidence=confidence,
                accepted=True,
                held=False,
                spectrum=np.asarray(smooth_spectrum, dtype=np.float64),
            )
        return self._held_or_empty(smooth_spectrum)

    def _held_or_empty(self, spectrum: np.ndarray) -> LocalizationResult:
        if self._last_accepted_angle_rad is not None and self._hold_remaining > 0:
            self._hold_remaining -= 1
            return LocalizationResult(
                doa_deg=float(np.degrees(self._last_accepted_angle_rad) % 360.0),
                confidence=float(max(0.0, self._last_accepted_score * 0.9)),
                accepted=False,
                held=True,
                spectrum=np.asarray(spectrum, dtype=np.float64),
            )
        return LocalizationResult(
            doa_deg=None,
            confidence=0.0,
            accepted=False,
            held=False,
            spectrum=np.asarray(spectrum, dtype=np.float64),
        )

    def _compute_stft_roi(self, audio_mic_first: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
        noverlap = min(int(round(self._nfft * self._overlap)), self._nfft - 1)
        freq_vec, _t_vec, zxx = signal.stft(
            audio_mic_first,
            fs=self._sample_rate_hz,
            nperseg=self._nfft,
            noverlap=noverlap,
            boundary=None,
            padded=False,
        )
        f_min, f_max = self._freq_range_hz
        eligible = np.flatnonzero((freq_vec >= f_min) & (freq_vec <= f_max))
        if eligible.size == 0:
            return None
        eligible = eligible[:: self._freq_bin_subsample_stride]
        relevant_freqs = np.asarray(freq_vec[eligible], dtype=np.float64)
        zxx_roi = np.asarray(zxx[:, eligible, :], dtype=np.complex128)
        if zxx_roi.shape[1] == 0 or zxx_roi.shape[2] == 0:
            return None
        return relevant_freqs, zxx_roi

    def _search_angles_for_update(self) -> tuple[np.ndarray, bool]:
        self._update_counter += 1
        full_scan = (
            (not self._local_refine_enabled)
            or self._last_accepted_angle_rad is None
            or self._full_scan_every_n_updates <= 1
            or ((self._update_counter - 1) % self._full_scan_every_n_updates == 0)
        )
        if full_scan:
            return np.linspace(0.0, 2.0 * np.pi, self._grid_size, endpoint=False, dtype=np.float64), True
        step_deg = max(360.0 / max(self._grid_size, 1), 0.5)
        offsets_deg = np.arange(
            -self._local_refine_half_width_deg,
            self._local_refine_half_width_deg + (0.5 * step_deg),
            step_deg,
            dtype=np.float64,
        )
        center_deg = float(np.degrees(float(self._last_accepted_angle_rad)) % 360.0)
        local_angles_deg = (center_deg + offsets_deg) % 360.0
        return np.deg2rad(local_angles_deg), False

    def _update_covariance_bank(self, relevant_freqs: np.ndarray, zxx_roi: np.ndarray) -> np.ndarray:
        n_mics = int(zxx_roi.shape[0])
        freq_count = int(zxx_roi.shape[1])
        if (
            self._covariance_accum is None
            or self._covariance_accum.shape != (freq_count, n_mics, n_mics)
            or self._covariance_freqs_hz is None
            or self._covariance_freqs_hz.shape != relevant_freqs.shape
            or not np.allclose(self._covariance_freqs_hz, relevant_freqs)
        ):
            self._covariance_accum = np.zeros((freq_count, n_mics, n_mics), dtype=np.complex128)
            self._covariance_freqs_hz = np.asarray(relevant_freqs, dtype=np.float64).copy()

        out = np.zeros_like(self._covariance_accum)
        use_ema = self._covariance_ema_alpha > 0.0
        for freq_idx in range(freq_count):
            snapshots = np.asarray(zxx_roi[:, freq_idx, :], dtype=np.complex128)
            if snapshots.ndim != 2 or snapshots.shape[1] == 0:
                continue
            cov_inst = (snapshots @ snapshots.conj().T) / max(1, snapshots.shape[1])
            if use_ema:
                prev = self._covariance_accum[freq_idx]
                cov = (self._covariance_ema_alpha * prev) + ((1.0 - self._covariance_ema_alpha) * cov_inst)
            else:
                cov = cov_inst
            self._covariance_accum[freq_idx] = cov
            out[freq_idx] = cov
        return out

    def _capon_spectrum_from_roi(
        self,
        relevant_freqs: np.ndarray,
        zxx_roi: np.ndarray,
        search_angles_rad: np.ndarray,
    ) -> np.ndarray:
        n_mics = int(zxx_roi.shape[0])
        directions = np.stack([np.cos(search_angles_rad), np.sin(search_angles_rad), np.zeros_like(search_angles_rad)], axis=1)
        spectrum = np.zeros((search_angles_rad.shape[0],), dtype=np.float64)
        eye = np.eye(n_mics, dtype=np.complex128)
        covariances = self._update_covariance_bank(relevant_freqs, zxx_roi)

        for freq_idx, freq_hz in enumerate(relevant_freqs):
            cov = covariances[freq_idx]
            if not np.any(cov):
                continue
            trace_scale = float(np.real(np.trace(cov))) / max(1, n_mics)
            load = max(self._diagonal_loading * max(trace_scale, 1e-8), 1e-8)
            cov_loaded = cov + (load * eye)

            mic_projections = self._mic_pos_xy.T @ directions[:, :2].T
            tau = mic_projections / float(self._sound_speed_m_s)
            tau = tau - np.mean(tau, axis=0, keepdims=True)
            steering = np.exp(-1j * 2.0 * np.pi * float(freq_hz) * tau)

            solved = None
            if self._use_cholesky_solve:
                try:
                    chol = cho_factor(cov_loaded, lower=False, check_finite=False, overwrite_a=False)
                    solved = cho_solve(chol, steering, check_finite=False)
                except Exception:
                    solved = None
            if solved is None:
                try:
                    solved = np.linalg.solve(cov_loaded, steering)
                except np.linalg.LinAlgError:
                    try:
                        cov_inv = np.linalg.pinv(cov_loaded, hermitian=True)
                    except TypeError:
                        cov_inv = np.linalg.pinv(cov_loaded)
                    solved = cov_inv @ steering

            numerators = np.einsum("ma,ma->a", steering.conj(), solved, optimize=True)
            denom = np.maximum(np.real(numerators), 1e-10)
            spectrum += 1.0 / denom

        spectrum = np.asarray(np.real(spectrum), dtype=np.float64)
        spectrum[~np.isfinite(spectrum)] = 0.0
        spectrum[spectrum < 0.0] = 0.0
        vmax = float(np.max(spectrum))
        if vmax > 0.0:
            spectrum /= vmax
        return spectrum

    def _smooth_spectrum(self, spectrum: np.ndarray) -> np.ndarray:
        arr = np.asarray(spectrum, dtype=np.float64)
        if self._spectrum_accum is None or self._spectrum_accum.shape != arr.shape:
            self._spectrum_accum = arr.copy()
        else:
            alpha = float(np.clip(self._spectrum_ema_alpha, 0.0, 0.98))
            self._spectrum_accum = (alpha * self._spectrum_accum) + ((1.0 - alpha) * arr)
        smooth = np.asarray(self._spectrum_accum, dtype=np.float64)
        vmax = float(np.max(smooth)) if smooth.size else 0.0
        if vmax > 0.0:
            smooth = smooth / vmax
        return smooth

    def _score_peak(self, spectrum: np.ndarray, *, exclusion_deg: float = 12.0) -> dict[str, float | int | bool | None]:
        smooth = np.asarray(spectrum, dtype=np.float64)
        peak_indices = _circular_local_maxima(smooth, min_separation_bins=1, max_peaks=1)
        best_idx = int(peak_indices[0]) if peak_indices else int(np.argmax(smooth))
        best_score = float(smooth[best_idx]) if smooth.size else 0.0
        left = float(smooth[(best_idx - 1) % smooth.size]) if smooth.size else 0.0
        right = float(smooth[(best_idx + 1) % smooth.size]) if smooth.size else 0.0
        local_baseline = max(left, right)
        global_baseline = float(np.median(smooth)) if smooth.size else 0.0
        local_contrast = float(max(0.0, best_score - local_baseline))
        peak_sharpness = float(max(0.0, best_score - global_baseline))

        second_idx = None
        second_score = 0.0
        exclusion_bins = max(2, int(round(float(exclusion_deg) / (360.0 / max(smooth.size, 1)))))
        for idx, score in sorted(enumerate(smooth.tolist()), key=lambda item: item[1], reverse=True):
            if abs(idx - best_idx) <= exclusion_bins or (smooth.size - abs(idx - best_idx)) <= exclusion_bins:
                continue
            second_idx = int(idx)
            second_score = float(score)
            break
        peak_margin = float(max(0.0, best_score - second_score))
        confidence = float(np.clip((0.5 * best_score) + (0.25 * peak_sharpness) + (0.25 * peak_margin), 0.0, 1.0))
        accepted = bool(peak_sharpness >= self._peak_min_sharpness and peak_margin >= self._peak_min_margin)
        return {
            "best_idx": int(best_idx),
            "best_score": float(best_score),
            "second_idx": None if second_idx is None else int(second_idx),
            "local_contrast": float(local_contrast),
            "peak_sharpness": float(peak_sharpness),
            "peak_margin": float(peak_margin),
            "confidence": float(confidence),
            "accepted": bool(accepted),
        }
