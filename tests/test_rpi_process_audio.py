from __future__ import annotations

import numpy as np
import pytest

from rpi import process_audio


class _FakeLocalizer:
    def __init__(self, *args, **kwargs) -> None:
        self.calls = 0

    def process(self, audio_window: np.ndarray):
        self.calls += 1
        return type(
            "LocalizationResult",
            (),
            {
                "doa_deg": 45.0,
                "confidence": 1.0,
                "accepted": True,
                "held": False,
                "spectrum": np.ones((72,), dtype=np.float64),
            },
        )()


class _FakeBeamformer:
    def __init__(self, *args, **kwargs) -> None:
        self.suppress_calls = 0
        self.beamform_calls = 0

    def beamform(self, frame_mc: np.ndarray, *, doa_deg: float | None):
        self.beamform_calls += 1
        mono = np.mean(frame_mc, axis=1).astype(np.float32, copy=False)
        return type("BeamformOutput", (), {"target": mono, "output": mono})()

    def suppress(self, frame_mc: np.ndarray, *, target_doa_deg: float | None, interferer_doa_deg: float | None):
        self.suppress_calls += 1
        mono = np.mean(frame_mc, axis=1).astype(np.float32, copy=False)
        return type("BeamformOutput", (), {"target": mono, "output": mono * 0.5})()


class _FakeDenoiser:
    def __init__(self, *args, **kwargs) -> None:
        self.calls = 0

    def process(self, frame: np.ndarray):
        self.calls += 1
        arr = np.asarray(frame, dtype=np.float32)
        return type("DenoiseResult", (), {"denoised": arr + 0.1, "residual": arr - 0.2})()


@pytest.fixture(autouse=True)
def _reset_pipeline(monkeypatch):
    monkeypatch.setattr(process_audio, "CaponLocalizer", _FakeLocalizer)
    monkeypatch.setattr(process_audio, "DelayAndSumBeamformer", _FakeBeamformer)
    monkeypatch.setattr(process_audio, "RNNoiseProcessor", _FakeDenoiser)
    process_audio._reset_processor_for_tests()
    yield
    process_audio._reset_processor_for_tests()


def _make_audio_bytes(frame_value: int = 1000, *, channels: int = 6) -> bytes:
    frame = np.full((160, channels), frame_value, dtype=np.int16)
    return frame.astype(np.int16).tobytes()


def test_process_audio_callback_rejects_invalid_frame_size() -> None:
    bad = np.zeros((159, 6), dtype=np.int16).tobytes()
    with pytest.raises(ValueError, match="expected 160 samples per channel"):
        process_audio.process_audio_callback(bad, 6)


def test_process_audio_callback_rejects_missing_required_channels() -> None:
    with pytest.raises(ValueError, match="expected at least 6 interleaved channels"):
        process_audio.process_audio_callback(_make_audio_bytes(channels=4), 4)


def test_process_audio_callback_returns_passthrough_during_warmup() -> None:
    out = process_audio.process_audio_callback(_make_audio_bytes(frame_value=1200), 6)
    out_arr = np.frombuffer(out, dtype=np.int16)
    assert out_arr.shape == (160,)
    assert np.all(np.abs(out_arr.astype(np.int32) - 1200) <= 1)


def test_process_audio_callback_uses_suppression_residual_after_warmup() -> None:
    for _ in range(19):
        process_audio.process_audio_callback(_make_audio_bytes(frame_value=1200), 6)
    out = process_audio.process_audio_callback(_make_audio_bytes(frame_value=1200), 6)
    out_arr = np.frombuffer(out, dtype=np.int16)
    expected = int(np.clip(0.5 * (1200 / 32768.0) - 0.2, -1.0, 1.0) * 32767.0)
    assert out_arr.shape == (160,)
    assert np.all(np.abs(out_arr.astype(np.int32) - expected) <= 1)
