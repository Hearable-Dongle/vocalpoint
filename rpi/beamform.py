from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _norm_deg(v: float) -> float:
    return float(v % 360.0)


def _wrap_to_180(v: float) -> float:
    return float((float(v) + 180.0) % 360.0 - 180.0)


def _angular_dist_deg(a: float, b: float) -> float:
    return abs(_wrap_to_180(float(a) - float(b)))


def _step_limited_angle(prev_deg: float, next_deg: float, max_step_deg: float) -> float:
    delta = _wrap_to_180(next_deg - prev_deg)
    step = float(np.clip(delta, -max_step_deg, max_step_deg))
    return _norm_deg(prev_deg + step)


def _ema_angle(prev_deg: float, new_deg: float, alpha: float) -> float:
    prev_rad = np.deg2rad(float(prev_deg))
    new_rad = np.deg2rad(float(new_deg))
    prev_vec = np.array([np.cos(prev_rad), np.sin(prev_rad)], dtype=np.float64)
    new_vec = np.array([np.cos(new_rad), np.sin(new_rad)], dtype=np.float64)
    merged = ((1.0 - alpha) * prev_vec) + (alpha * new_vec)
    if float(np.linalg.norm(merged)) < 1e-12:
        return _norm_deg(new_deg)
    return _norm_deg(np.degrees(np.arctan2(merged[1], merged[0])))


def _fractional_delay_shift(x: np.ndarray, delay_samples: float) -> np.ndarray:
    arr = np.asarray(x, dtype=np.float64)
    sample_idx = np.arange(arr.shape[0], dtype=np.float64)
    source_idx = sample_idx - float(delay_samples)
    return np.interp(source_idx, sample_idx, arr, left=0.0, right=0.0)


def delay_and_sum_frame(
    frame_mc: np.ndarray,
    *,
    doa_deg: float,
    mic_geometry_xyz: np.ndarray,
    sample_rate_hz: int,
    sound_speed_m_s: float,
) -> np.ndarray:
    frame = np.asarray(frame_mc, dtype=np.float64)
    if frame.ndim != 2:
        raise ValueError("frame_mc must be shape (samples, n_mics)")

    mic_pos = np.asarray(mic_geometry_xyz, dtype=np.float64)
    if mic_pos.shape[0] == 3:
        mic_pos = mic_pos.T
    if mic_pos.shape[1] == 2:
        mic_pos = np.hstack([mic_pos, np.zeros((mic_pos.shape[0], 1), dtype=np.float64)])

    azimuth = np.deg2rad(float(doa_deg))
    direction = np.array([-np.cos(azimuth), -np.sin(azimuth), 0.0], dtype=np.float64)
    tau = (mic_pos @ direction) / float(sound_speed_m_s)
    tau = tau - float(np.mean(tau))
    delays = tau * float(sample_rate_hz)

    aligned = np.zeros((frame.shape[0],), dtype=np.float64)
    for mic_idx in range(frame.shape[1]):
        aligned += _fractional_delay_shift(frame[:, mic_idx], float(delays[mic_idx]))
    return (aligned / max(1, frame.shape[1])).astype(np.float32, copy=False)


@dataclass(slots=True)
class BeamformOutput:
    target: np.ndarray
    output: np.ndarray


class DelayAndSumBeamformer:
    def __init__(
        self,
        *,
        mic_geometry_xyz: np.ndarray,
        sample_rate_hz: int = 16000,
        sound_speed_m_s: float = 343.0,
        doa_ema_alpha: float = 0.2,
        doa_max_step_deg_per_frame: float = 10.0,
        update_min_delta_deg: float = 3.0,
        crossfade_frames: int = 1,
        subtractive_alpha: float = 0.5,
        subtractive_multi_offset_deg: float = 10.0,
        subtractive_silence_guard_enabled: bool = True,
        subtractive_silence_guard_ratio_threshold: float = 0.15,
        subtractive_silence_guard_target_rms_floor: float = 0.005,
        subtractive_spike_guard_enabled: bool = True,
        subtractive_spike_guard_sample_jump_threshold: float = 0.25,
        subtractive_output_crossfade_enabled: bool = False,
        subtractive_output_crossfade_samples: int = 16,
        subtractive_declick_enabled: bool = False,
        subtractive_declick_alpha: float = 0.9,
        subtractive_declick_spike_threshold: float = 0.08,
        subtractive_interferer_ema_enabled: bool = False,
        subtractive_interferer_ema_alpha: float = 0.7,
        subtractive_adaptive_alpha_enabled: bool = False,
        subtractive_adaptive_alpha_min: float = 0.2,
        subtractive_adaptive_alpha_delta_scale: float = 1.0,
    ) -> None:
        self._mic_geometry_xyz = np.asarray(mic_geometry_xyz, dtype=np.float64)
        self._sample_rate_hz = int(sample_rate_hz)
        self._sound_speed_m_s = float(sound_speed_m_s)
        self._doa_ema_alpha = float(np.clip(doa_ema_alpha, 0.0, 1.0))
        self._doa_max_step_deg_per_frame = float(max(0.1, doa_max_step_deg_per_frame))
        self._update_min_delta_deg = float(max(0.0, update_min_delta_deg))
        self._crossfade_frames = max(1, int(crossfade_frames))
        self._subtractive_alpha = float(max(0.0, subtractive_alpha))
        self._subtractive_multi_offset_deg = float(max(0.0, subtractive_multi_offset_deg))
        self._subtractive_silence_guard_enabled = bool(subtractive_silence_guard_enabled)
        self._subtractive_silence_guard_ratio_threshold = float(max(0.0, subtractive_silence_guard_ratio_threshold))
        self._subtractive_silence_guard_target_rms_floor = float(max(0.0, subtractive_silence_guard_target_rms_floor))
        self._subtractive_spike_guard_enabled = bool(subtractive_spike_guard_enabled)
        self._subtractive_spike_guard_sample_jump_threshold = float(max(0.0, subtractive_spike_guard_sample_jump_threshold))
        self._subtractive_output_crossfade_enabled = bool(subtractive_output_crossfade_enabled)
        self._subtractive_output_crossfade_samples = max(0, int(subtractive_output_crossfade_samples))
        self._subtractive_declick_enabled = bool(subtractive_declick_enabled)
        self._subtractive_declick_alpha = float(np.clip(subtractive_declick_alpha, 0.0, 0.9999))
        self._subtractive_declick_spike_threshold = float(max(0.0, subtractive_declick_spike_threshold))
        self._subtractive_interferer_ema_enabled = bool(subtractive_interferer_ema_enabled)
        self._subtractive_interferer_ema_alpha = float(np.clip(subtractive_interferer_ema_alpha, 0.0, 1.0))
        self._subtractive_adaptive_alpha_enabled = bool(subtractive_adaptive_alpha_enabled)
        self._subtractive_adaptive_alpha_min = float(np.clip(subtractive_adaptive_alpha_min, 0.0, 1.0))
        self._subtractive_adaptive_alpha_delta_scale = float(max(subtractive_adaptive_alpha_delta_scale, 1e-6))

        self._delay_sum_state_by_key: dict[str, dict[str, float | int | None]] = {}
        self._subtractive_last_good_by_key: dict[str, np.ndarray] = {}
        self._subtractive_prev_output_by_key: dict[str, np.ndarray] = {}
        self._subtractive_prev_interferer_by_key: dict[str, np.ndarray] = {}
        self._subtractive_prev_declick_sample_by_key: dict[str, float] = {}

    def beamform(self, frame_mc: np.ndarray, *, doa_deg: float | None) -> BeamformOutput:
        frame = np.asarray(frame_mc, dtype=np.float32)
        if doa_deg is None:
            mono = np.mean(frame, axis=1).astype(np.float32, copy=False)
            return BeamformOutput(target=mono, output=mono)
        target = self._delay_sum_with_state(frame, doa_deg=float(doa_deg), state_key="primary")
        return BeamformOutput(target=target, output=target)

    def suppress(self, frame_mc: np.ndarray, *, target_doa_deg: float | None, interferer_doa_deg: float | None) -> BeamformOutput:
        frame = np.asarray(frame_mc, dtype=np.float32)
        if target_doa_deg is None:
            mono = np.mean(frame, axis=1).astype(np.float32, copy=False)
            return BeamformOutput(target=mono, output=mono)
        target = self._delay_sum_with_state(frame, doa_deg=float(target_doa_deg), state_key="subtractive_target")
        if interferer_doa_deg is None:
            return BeamformOutput(target=target, output=target)

        interferer = self._delay_sum_with_state(frame, doa_deg=float(interferer_doa_deg), state_key="subtractive_interferer")
        interferer, delta = self._stabilize_subtractive_interferer(state_key="subtractive_interferer", interferer=interferer)
        alpha = self._adaptive_subtractive_alpha(base_alpha=self._subtractive_alpha, delta=delta)
        out = np.asarray(target, dtype=np.float32) - (alpha * np.asarray(interferer, dtype=np.float32))
        peak = float(np.max(np.abs(out))) if out.size else 0.0
        if peak > 1.0:
            out = out / peak
        out = self._apply_subtractive_declick(state_key="subtractive_out", out=out)
        out = self._apply_subtractive_output_crossfade(state_key="subtractive_out", out=out)
        out = self._apply_subtractive_output_guards(state_key="subtractive_out", target=target, out=out)
        return BeamformOutput(target=target, output=np.asarray(out, dtype=np.float32))

    def _delay_sum_candidate_doa(self, *, state: dict[str, float | int | None], doa_deg: float) -> float:
        candidate = _norm_deg(float(doa_deg))
        prev_smoothed = state.get("smoothed_doa_deg")
        if prev_smoothed is None:
            state["smoothed_doa_deg"] = candidate
            return candidate
        limited = _step_limited_angle(float(prev_smoothed), candidate, self._doa_max_step_deg_per_frame)
        smoothed = _ema_angle(float(prev_smoothed), limited, self._doa_ema_alpha)
        state["smoothed_doa_deg"] = smoothed
        return float(smoothed)

    def _delay_sum_with_state(self, frame_mc: np.ndarray, *, doa_deg: float, state_key: str) -> np.ndarray:
        state = self._delay_sum_state_by_key.setdefault(
            str(state_key),
            {
                "applied_doa_deg": None,
                "smoothed_doa_deg": None,
                "transition_from_doa_deg": None,
                "transition_to_doa_deg": None,
                "transition_frame_idx": 0,
                "transition_total_frames": 0,
            },
        )
        candidate_doa = self._delay_sum_candidate_doa(state=state, doa_deg=float(doa_deg))
        applied_doa = state.get("applied_doa_deg")
        if applied_doa is None:
            state["applied_doa_deg"] = candidate_doa
            return delay_and_sum_frame(
                frame_mc,
                doa_deg=float(candidate_doa),
                mic_geometry_xyz=self._mic_geometry_xyz,
                sample_rate_hz=self._sample_rate_hz,
                sound_speed_m_s=self._sound_speed_m_s,
            )

        if _angular_dist_deg(float(applied_doa), float(candidate_doa)) < self._update_min_delta_deg:
            candidate_doa = float(applied_doa)

        transition_total_frames = int(state.get("transition_total_frames", 0) or 0)
        transition_frame_idx = int(state.get("transition_frame_idx", 0) or 0)
        transition_from_doa = state.get("transition_from_doa_deg")
        transition_to_doa = state.get("transition_to_doa_deg")

        if candidate_doa != float(applied_doa):
            if transition_total_frames <= 0 or transition_to_doa is None or _angular_dist_deg(float(transition_to_doa), float(candidate_doa)) >= self._update_min_delta_deg:
                state["transition_from_doa_deg"] = float(applied_doa)
                state["transition_to_doa_deg"] = float(candidate_doa)
                state["transition_frame_idx"] = 0
                state["transition_total_frames"] = self._crossfade_frames
                transition_total_frames = self._crossfade_frames
                transition_frame_idx = 0
                transition_from_doa = float(applied_doa)
                transition_to_doa = float(candidate_doa)

        if transition_total_frames > 0 and transition_from_doa is not None and transition_to_doa is not None:
            old_out = delay_and_sum_frame(
                frame_mc,
                doa_deg=float(transition_from_doa),
                mic_geometry_xyz=self._mic_geometry_xyz,
                sample_rate_hz=self._sample_rate_hz,
                sound_speed_m_s=self._sound_speed_m_s,
            )
            new_out = delay_and_sum_frame(
                frame_mc,
                doa_deg=float(transition_to_doa),
                mic_geometry_xyz=self._mic_geometry_xyz,
                sample_rate_hz=self._sample_rate_hz,
                sound_speed_m_s=self._sound_speed_m_s,
            )
            sample_progress = np.linspace(
                float(transition_frame_idx) / float(transition_total_frames),
                float(transition_frame_idx + 1) / float(transition_total_frames),
                num=int(old_out.shape[0]),
                endpoint=True,
                dtype=np.float32,
            )
            out = ((1.0 - sample_progress) * old_out.astype(np.float32)) + (sample_progress * new_out.astype(np.float32))
            transition_frame_idx += 1
            if transition_frame_idx >= transition_total_frames:
                state["applied_doa_deg"] = float(transition_to_doa)
                state["transition_from_doa_deg"] = None
                state["transition_to_doa_deg"] = None
                state["transition_frame_idx"] = 0
                state["transition_total_frames"] = 0
            else:
                state["transition_frame_idx"] = transition_frame_idx
            return np.asarray(out, dtype=np.float32)

        return delay_and_sum_frame(
            frame_mc,
            doa_deg=float(candidate_doa),
            mic_geometry_xyz=self._mic_geometry_xyz,
            sample_rate_hz=self._sample_rate_hz,
            sound_speed_m_s=self._sound_speed_m_s,
        )

    def _apply_subtractive_output_guards(self, *, state_key: str, target: np.ndarray, out: np.ndarray) -> np.ndarray:
        guarded = np.asarray(out, dtype=np.float32)
        target_rms = float(np.sqrt(np.mean(np.asarray(target, dtype=np.float64) ** 2) + 1e-12))
        out_rms = float(np.sqrt(np.mean(np.asarray(guarded, dtype=np.float64) ** 2) + 1e-12))
        prev = self._subtractive_last_good_by_key.get(state_key)
        silence_bad = False
        if self._subtractive_silence_guard_enabled:
            silence_bad = (
                target_rms >= self._subtractive_silence_guard_target_rms_floor
                and out_rms <= (self._subtractive_silence_guard_ratio_threshold * target_rms)
            )
        spike_bad = False
        if self._subtractive_spike_guard_enabled and prev is not None and prev.shape == guarded.shape and prev.size and guarded.size:
            sample_jump = float(guarded[0]) - float(prev[-1])
            spike_bad = sample_jump > self._subtractive_spike_guard_sample_jump_threshold
        if (silence_bad or spike_bad) and prev is not None and prev.shape == guarded.shape:
            return prev.copy()
        if guarded.size:
            self._subtractive_last_good_by_key[state_key] = guarded.copy()
        return guarded

    def _stabilize_subtractive_interferer(self, *, state_key: str, interferer: np.ndarray) -> tuple[np.ndarray, float]:
        cur = np.asarray(interferer, dtype=np.float32)
        prev = self._subtractive_prev_interferer_by_key.get(state_key)
        delta = 0.0
        if prev is not None and prev.shape == cur.shape and prev.size:
            denom = float(np.sqrt(np.mean(np.asarray(prev, dtype=np.float64) ** 2) + 1e-12))
            delta = float(np.sqrt(np.mean(np.asarray(cur - prev, dtype=np.float64) ** 2) + 1e-12)) / max(denom, 1e-6)
            if self._subtractive_interferer_ema_enabled:
                alpha = self._subtractive_interferer_ema_alpha
                cur = (((1.0 - alpha) * prev.astype(np.float32)) + (alpha * cur)).astype(np.float32, copy=False)
        self._subtractive_prev_interferer_by_key[state_key] = cur.copy()
        return cur, float(delta)

    def _adaptive_subtractive_alpha(self, *, base_alpha: float, delta: float) -> float:
        if not self._subtractive_adaptive_alpha_enabled:
            return float(base_alpha)
        shrink = 1.0 / (1.0 + (self._subtractive_adaptive_alpha_delta_scale * max(delta, 0.0)))
        return float(np.clip(base_alpha * shrink, self._subtractive_adaptive_alpha_min, base_alpha))

    def _apply_subtractive_declick(self, *, state_key: str, out: np.ndarray) -> np.ndarray:
        y = np.asarray(out, dtype=np.float32).copy()
        if not self._subtractive_declick_enabled:
            if y.size:
                self._subtractive_prev_declick_sample_by_key[state_key] = float(y[-1])
            return y
        prev = float(self._subtractive_prev_declick_sample_by_key.get(state_key, 0.0))
        for idx in range(y.shape[0]):
            cur = float(y[idx])
            if abs(cur - prev) > self._subtractive_declick_spike_threshold:
                cur = float((self._subtractive_declick_alpha * prev) + ((1.0 - self._subtractive_declick_alpha) * cur))
                y[idx] = cur
            prev = cur
        self._subtractive_prev_declick_sample_by_key[state_key] = prev
        return y

    def _apply_subtractive_output_crossfade(self, *, state_key: str, out: np.ndarray) -> np.ndarray:
        y = np.asarray(out, dtype=np.float32).copy()
        prev = self._subtractive_prev_output_by_key.get(state_key)
        if not self._subtractive_output_crossfade_enabled or prev is None or prev.shape != y.shape or y.size == 0:
            self._subtractive_prev_output_by_key[state_key] = y.copy()
            return y
        fade_len = min(
            self._subtractive_output_crossfade_samples,
            y.shape[0] // 4,
            prev.shape[0],
            y.shape[0],
        )
        if fade_len > 0:
            fade_out = np.linspace(1.0, 0.0, fade_len, endpoint=True, dtype=np.float32)
            fade_in = np.linspace(0.0, 1.0, fade_len, endpoint=True, dtype=np.float32)
            y[:fade_len] = (prev[-fade_len:] * fade_out) + (y[:fade_len] * fade_in)
        self._subtractive_prev_output_by_key[state_key] = y.copy()
        return y
