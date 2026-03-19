from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_CHANNEL_MAP = (2, 3, 4, 5)
_INPUT_SAMPLE_RATE_HZ = 16000
_EXPECTED_FRAME_SAMPLES = 160
_OWN_VOICE_SUPPRESSION_ENABLED = True
_OWN_VOICE_SUPPRESSION_DOA_DEG = 45
_ADAPTER = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_submodule_import_path() -> None:
    submodule_root = _repo_root() / "signal-processing-research"
    if not submodule_root.is_dir():
        raise ModuleNotFoundError(f"signal-processing-research submodule not found at {submodule_root}")
    submodule_path = str(submodule_root)
    if submodule_path not in sys.path:
        sys.path.insert(0, submodule_path)


def _load_adapter_class():
    _ensure_submodule_import_path()
    from realtime_pipeline import RealtimeIntelligibilityAdapter

    return RealtimeIntelligibilityAdapter


def _get_adapter():
    global _ADAPTER
    if _ADAPTER is None:
        adapter_class = _load_adapter_class()
        _ADAPTER = adapter_class(
            input_sample_rate_hz=_INPUT_SAMPLE_RATE_HZ,
            own_voice_suppression_enabled=_OWN_VOICE_SUPPRESSION_ENABLED,
            own_voice_suppression_doa_deg=_OWN_VOICE_SUPPRESSION_DOA_DEG,
        )
    return _ADAPTER


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


def _select_adapter_channels(interleaved: np.ndarray) -> list[np.ndarray]:
    channel_count = int(interleaved.shape[1])
    required_channels = max(_CHANNEL_MAP) + 1
    if channel_count < required_channels:
        raise ValueError(
            f"expected at least {required_channels} interleaved channels to map {_CHANNEL_MAP}, got {channel_count}"
        )

    return [np.ascontiguousarray(interleaved[:, idx], dtype=np.int16) for idx in _CHANNEL_MAP]


def _float32_mono_to_pcm16_bytes(audio_mono: np.ndarray, expected_samples: int) -> bytes:
    mono = np.asarray(audio_mono, dtype=np.float32).reshape(-1)
    if mono.shape[0] != expected_samples:
        raise ValueError(f"adapter returned {mono.shape[0]} mono samples, expected {expected_samples}")

    clipped = np.clip(mono * 32767.0, -32768.0, 32767.0)
    return clipped.astype(np.int16).tobytes()


def process_callback_audio(audio_bytes: bytes, channels: int) -> bytes:
    interleaved = _decode_interleaved_channels(audio_bytes, channels)
    selected_channels = _select_adapter_channels(interleaved)
    mono_float32 = _get_adapter().process_chunk(selected_channels)
    return _float32_mono_to_pcm16_bytes(mono_float32, expected_samples=interleaved.shape[0])
