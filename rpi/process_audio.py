from __future__ import annotations

import threading

import numpy as np

try:
    from .beamform import DelayAndSumBeamformer
    from .denoise import RNNoiseProcessor
    from .localization import CaponLocalizer
except ImportError:  # pragma: no cover
    from beamform import DelayAndSumBeamformer
    from denoise import RNNoiseProcessor
    from localization import CaponLocalizer


_CHANNEL_MAP = (2, 3, 4, 5)
_INPUT_SAMPLE_RATE_HZ = 16000
_EXPECTED_FRAME_SAMPLES = 160
_LOCALIZATION_WINDOW_MS = 200
_MIC_ARRAY_RADIUS_M = 0.065 / 2.0
_MIC_GEOMETRY_XYZ = np.array(
    [
        [_MIC_ARRAY_RADIUS_M, _MIC_ARRAY_RADIUS_M, 0.0],
        [-_MIC_ARRAY_RADIUS_M, _MIC_ARRAY_RADIUS_M, 0.0],
        [-_MIC_ARRAY_RADIUS_M, -_MIC_ARRAY_RADIUS_M, 0.0],
        [_MIC_ARRAY_RADIUS_M, -_MIC_ARRAY_RADIUS_M, 0.0],
    ],
    dtype=np.float64,
)
_OWN_VOICE_SUPPRESSION_ENABLED = True
_OWN_VOICE_SUPPRESSION_DOA_DEG = 335.0

_PROCESSOR = None
_PROCESSOR_LOCK = threading.Lock()


def _decode_interleaved_channels(audio_bytes: bytes, channels: int) -> np.ndarray:
    if channels <= 0:
        raise ValueError(f"channels must be positive, got {channels}")
    audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
    if audio_int16.size % channels != 0:
        raise ValueError(
            f"invalid interleaved PCM16 buffer: {audio_int16.size} samples is not divisible by {channels} channels"
        )
    samples_per_channel = audio_int16.size // channels
    if samples_per_channel != _EXPECTED_FRAME_SAMPLES:
        raise ValueError(
            f"expected {_EXPECTED_FRAME_SAMPLES} samples per channel per callback, got {samples_per_channel}"
        )
    return audio_int16.reshape(samples_per_channel, channels)


def _select_pipeline_channels(interleaved: np.ndarray) -> list[np.ndarray]:
    channel_count = int(interleaved.shape[1])
    required_channels = max(_CHANNEL_MAP) + 1
    if channel_count < required_channels:
        raise ValueError(
            f"expected at least {required_channels} interleaved channels to map {_CHANNEL_MAP}, got {channel_count}"
        )
    return [np.ascontiguousarray(interleaved[:, idx], dtype=np.int16) for idx in _CHANNEL_MAP]


def _int16_channels_to_float32_frame(channels: list[np.ndarray]) -> np.ndarray:
    if not channels:
        raise ValueError("channels must contain at least one channel")
    lengths = {int(np.asarray(channel).shape[0]) for channel in channels}
    if len(lengths) != 1:
        raise ValueError("all selected channels must have the same frame length")
    return (np.stack(channels, axis=1).astype(np.float32) / 32768.0).astype(np.float32, copy=False)


def _float32_mono_to_pcm16_bytes(audio_mono: np.ndarray, expected_samples: int) -> bytes:
    mono = np.asarray(audio_mono, dtype=np.float32).reshape(-1)
    if mono.shape[0] != expected_samples:
        raise ValueError(f"processor returned {mono.shape[0]} mono samples, expected {expected_samples}")
    clipped = np.clip(mono * 32767.0, -32768.0, 32767.0)
    return clipped.astype(np.int16).tobytes()


def _rms_normalize_to_input(
    output_mono: np.ndarray,
    input_channels: list[np.ndarray],
    eps: float = 1e-6,
) -> np.ndarray:
    input_rms = float(np.mean([np.sqrt(np.mean(ch.astype(np.float32) ** 2)) for ch in input_channels]))
    output_f32 = np.asarray(output_mono, dtype=np.float32)
    output_rms = float(np.sqrt(np.mean(output_f32**2)))
    gain = input_rms / (output_rms + eps)
    return output_f32 * gain


class RealtimeProcessAudioPipeline:
    def __init__(self) -> None:
        self._history_samples = max(1, int(round(_INPUT_SAMPLE_RATE_HZ * (_LOCALIZATION_WINDOW_MS / 1000.0))))
        self._history_mc = np.zeros((0, len(_CHANNEL_MAP)), dtype=np.float32)
        self._localizer = CaponLocalizer(
            mic_positions_xyz=_MIC_GEOMETRY_XYZ,
            sample_rate_hz=_INPUT_SAMPLE_RATE_HZ,
            nfft=512,
            overlap=0.5,
            freq_range_hz=(200, 3000),
            grid_size=72,
            diagonal_loading=1e-3,
            spectrum_ema_alpha=0.78,
            peak_min_sharpness=0.12,
            peak_min_margin=0.04,
            hold_frames=2,
            freq_bin_subsample_stride=1,
            use_cholesky_solve=False,
            covariance_ema_alpha=0.0,
            full_scan_every_n_updates=1,
            local_refine_enabled=False,
        )
        self._beamformer = DelayAndSumBeamformer(
            mic_geometry_xyz=_MIC_GEOMETRY_XYZ,
            sample_rate_hz=_INPUT_SAMPLE_RATE_HZ,
            sound_speed_m_s=343.0,
            doa_ema_alpha=0.2,
            doa_max_step_deg_per_frame=10.0,
            update_min_delta_deg=3.0,
            crossfade_frames=1,
            subtractive_alpha=0.5,
        )
        self._denoiser = RNNoiseProcessor(
            sample_rate_hz=_INPUT_SAMPLE_RATE_HZ,
            frame_ms=10,
            wet_mix=0.9,
            input_gain_db=0.0,
            input_highpass_enabled=True,
            input_highpass_cutoff_hz=80.0,
            output_highpass_enabled=True,
            output_highpass_cutoff_hz=80.0,
            output_lowpass_cutoff_hz=0.0,
            output_notch_freq_hz=0.0,
            output_notch_q=0.0,
            vad_adaptive_blend_enabled=True,
            vad_blend_gamma=0.5,
            vad_min_speech_preserve=0.15,
            vad_max_speech_preserve=0.95,
            startup_warmup_enabled=False,
            startup_warmup_frames=10,
            chunk_crossfade_enabled=False,
            chunk_crossfade_samples=16,
            declick_enabled=False,
            declick_alpha=0.92,
            declick_conditional=True,
            declick_spike_threshold=0.03,
            output_clip_guard_enabled=False,
            output_clip_guard_abs_max=0.95,
            corruption_guard_enabled=False,
            corruption_guard_rms_ratio_threshold=2.0,
            corruption_guard_peak_ratio_threshold=3.0,
            corruption_guard_mode="hold_previous",
            voice_eq_enabled=False,
        )
        self._lock = threading.RLock()

    def process_frame(self, frame_mc: np.ndarray) -> np.ndarray:
        with self._lock:
            frame = np.asarray(frame_mc, dtype=np.float32)
            if frame.ndim != 2 or frame.shape[1] != len(_CHANNEL_MAP):
                raise ValueError("frame_mc must be shape (samples, 4)")
            passthrough = np.mean(frame, axis=1).astype(np.float32, copy=False)
            self._append_history(frame)
            if self._history_mc.shape[0] < self._history_samples:
                return passthrough

            localization = self._localizer.process(self._history_mc)
            if _OWN_VOICE_SUPPRESSION_ENABLED:
                beamformed = self._beamformer.suppress(
                    frame,
                    target_doa_deg=localization.doa_deg,
                    interferer_doa_deg=_OWN_VOICE_SUPPRESSION_DOA_DEG,
                )
            else:
                beamformed = self._beamformer.beamform(frame, doa_deg=localization.doa_deg)
            denoised = self._denoiser.process(beamformed.output)
            if _OWN_VOICE_SUPPRESSION_ENABLED:
                return np.asarray(denoised.residual, dtype=np.float32)
            return np.asarray(denoised.denoised, dtype=np.float32)

    def _append_history(self, frame_mc: np.ndarray) -> None:
        if self._history_mc.size == 0:
            self._history_mc = np.asarray(frame_mc, dtype=np.float32)
        else:
            self._history_mc = np.concatenate([self._history_mc, np.asarray(frame_mc, dtype=np.float32)], axis=0)
        if self._history_mc.shape[0] > self._history_samples:
            self._history_mc = self._history_mc[-self._history_samples :, :]


def _get_processor() -> RealtimeProcessAudioPipeline:
    global _PROCESSOR
    if _PROCESSOR is None:
        with _PROCESSOR_LOCK:
            if _PROCESSOR is None:
                _PROCESSOR = RealtimeProcessAudioPipeline()
    return _PROCESSOR


def _reset_processor_for_tests() -> None:
    global _PROCESSOR
    with _PROCESSOR_LOCK:
        _PROCESSOR = None


def process_audio_callback(audio_bytes: bytes, channels: int, normalize_rms: bool = False) -> bytes:
    interleaved = _decode_interleaved_channels(audio_bytes, channels)
    selected_channels = _select_pipeline_channels(interleaved)
    frame_mc = _int16_channels_to_float32_frame(selected_channels)
    mono_float32 = _get_processor().process_frame(frame_mc)
    if normalize_rms:
        mono_float32 = _rms_normalize_to_input(mono_float32, selected_channels)
    return _float32_mono_to_pcm16_bytes(mono_float32, expected_samples=interleaved.shape[0])
