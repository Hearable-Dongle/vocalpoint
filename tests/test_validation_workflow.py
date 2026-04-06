from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np

from validate import common as validation_common

SIGNAL_PROCESSING_RESEARCH_ROOT = Path(__file__).resolve().parents[1] / "signal-processing-research"
if str(SIGNAL_PROCESSING_RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(SIGNAL_PROCESSING_RESEARCH_ROOT))

from validation import common as collection_common


def _write_recording(base: Path, *, recording_id: str, distance_m: float | None, direction_deg: float, channels: int = 6, samples: int = 320) -> Path:
    record_dir = base / recording_id
    raw_dir = record_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for channel_index in range(channels):
        audio = np.full((samples,), 1000 + (channel_index * 10), dtype=np.int16)
        validation_common.wavfile.write(raw_dir / f"channel_{channel_index:03d}.wav", 16000, audio)
    metadata = {
        "recordingId": recording_id,
        "sessionId": recording_id,
        "status": "ready",
        "deviceName": "ReSpeaker3000",
        "micArrayProfile": "ReSpeaker3000",
        "speakers": [] if distance_m is None else [{"speakerName": "speaker-a", "speakingPeriods": [{"startSec": 0.0, "endSec": 0.02, "directionDeg": direction_deg}]}],
        "artifacts": {
            "sampleRateHz": 16000,
            "channels": [{"channelIndex": idx, "filename": f"channel_{idx:03d}.wav"} for idx in range(channels)],
        },
        "validation": {"distanceM": distance_m} if distance_m is not None else {"noiseOnly": True},
    }
    (record_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return record_dir


def test_mix_speaker_and_noise_rms_matches_then_averages() -> None:
    speaker = np.ones((160, 6), dtype=np.float32) * 0.2
    noise = np.ones((160, 6), dtype=np.float32) * 0.05
    mixed = validation_common.mix_speaker_and_noise(speaker, noise, channel_map=(1, 2, 3, 4))
    assert mixed.shape == speaker.shape
    expected = np.ones((160, 6), dtype=np.float32) * 0.2
    assert np.allclose(mixed, expected, atol=1e-6)


def test_mix_speaker_and_noise_noise_scale_applies_after_rms_match() -> None:
    speaker = np.ones((160, 6), dtype=np.float32) * 0.2
    noise = np.ones((160, 6), dtype=np.float32) * 0.05
    mixed = validation_common.mix_speaker_and_noise(speaker, noise, channel_map=(1, 2, 3, 4), noise_scale=2.0)
    expected = np.ones((160, 6), dtype=np.float32) * 0.3
    assert np.allclose(mixed, expected, atol=1e-6)


def test_aggregate_results_by_distance_computes_stats() -> None:
    rows = [
        {"distance_m": 1.0, "sii_processed": 0.4, "snr_processed": 1.0},
        {"distance_m": 1.0, "sii_processed": 0.6, "snr_processed": 3.0},
        {"distance_m": 2.0, "sii_processed": 0.2, "snr_processed": 5.0},
    ]
    summary = validation_common.aggregate_results_by_distance(rows)
    assert summary[0]["distance_m"] == 1.0
    assert summary[0]["count"] == 2
    assert abs(float(summary[0]["sii_mean"]) - 0.5) < 1e-6
    assert abs(float(summary[0]["snr_median"]) - 2.0) < 1e-6
    assert summary[1]["distance_m"] == 2.0
    assert summary[1]["count"] == 1


def test_generate_white_noise_like_matches_shape_and_seed() -> None:
    reference = np.zeros((160, 6), dtype=np.float32)
    a = validation_common.generate_white_noise_like(reference, seed=7)
    b = validation_common.generate_white_noise_like(reference, seed=7)
    c = validation_common.generate_white_noise_like(reference, seed=8)
    assert a.shape == reference.shape
    assert np.allclose(a, b)
    assert not np.allclose(a, c)
    assert 0.17 < float(np.std(a)) < 0.33


def test_reference_and_raw_mono_use_active_channels_only() -> None:
    speaker_dir = _write_recording(Path("/tmp") / "validation-speaker-fixture", recording_id="speaker-002", distance_m=1.0, direction_deg=0.0)
    speaker_recording = validation_common.load_recording(speaker_dir)
    speaker_mc = validation_common.recording_to_multichannel_float32(speaker_recording)
    speaker_mc[:, 0] = 0.95
    speaker_mc[:, 5] = -0.95

    channel_map = validation_common.active_channel_map_for_recording(speaker_recording)
    ref_mono = validation_common.reference_mono_from_speaker(speaker_mc, channel_map=channel_map)
    raw_mono = validation_common.degraded_raw_mono_from_mix(speaker_mc, channel_map=channel_map)

    expected = np.mean(speaker_mc[:, [1, 2, 3, 4]], axis=1)
    assert np.allclose(ref_mono, expected)
    assert np.allclose(raw_mono, expected)


def test_default_capture_output_paths_are_generated_from_metadata() -> None:
    speaker_path = collection_common.default_speaker_output_path(
        speaker_id="test-matthew",
        distance_m=0.5,
        doa_deg=0.0,
    )
    noise_path = collection_common.default_noise_output_path(identifier="room tone A")
    assert re.fullmatch(r"ReSpeaker3000/test-matthew_d0p5m_doa0deg_[0-9a-f]{8}", speaker_path)
    assert re.fullmatch(r"ReSpeaker3000/room-tone-a_[0-9a-f]{8}", noise_path)


def test_evaluate_mode_uses_local_pipeline_runner(monkeypatch, tmp_path: Path) -> None:
    speaker_dir = _write_recording(tmp_path / "speakers", recording_id="speaker-001", distance_m=1.5, direction_deg=30.0)
    noise_dir = _write_recording(tmp_path / "noise", recording_id="noise-001", distance_m=None, direction_deg=0.0)
    speaker_recording = validation_common.load_recording(speaker_dir)
    noise_recording = validation_common.load_recording(noise_dir)
    speaker_mc, noise_mc = validation_common.align_recordings(speaker_recording, noise_recording)
    mix_mc = validation_common.mix_speaker_and_noise(
        speaker_mc,
        noise_mc,
        channel_map=validation_common.active_channel_map_for_recording(speaker_recording),
    )
    clean_ref_mono = validation_common.reference_mono_from_speaker(
        speaker_mc,
        channel_map=validation_common.active_channel_map_for_recording(speaker_recording),
    )

    captured = {}

    def fake_process_multichannel_audio(audio_mc, *, sample_rate_hz, mic_profile_name, own_voice_suppression_enabled, own_voice_suppression_doa_deg):
        captured["sample_rate_hz"] = sample_rate_hz
        captured["mic_profile_name"] = mic_profile_name
        captured["suppression_enabled"] = own_voice_suppression_enabled
        captured["suppression_doa_deg"] = own_voice_suppression_doa_deg
        return np.mean(audio_mc, axis=1).astype(np.float32) * (0.1 if own_voice_suppression_enabled else 0.8)

    monkeypatch.setattr(validation_common, "process_multichannel_audio", fake_process_multichannel_audio)

    result = validation_common.evaluate_mode(
        mix_mc=mix_mc,
        clean_ref_mono=clean_ref_mono,
        speaker_recording=speaker_recording,
        mode="own_voice_suppression",
        suppression_enabled=True,
        suppression_doa_deg=30.0,
        processing_mode="local",
    )

    assert captured["sample_rate_hz"] == 16000
    assert captured["mic_profile_name"] == "ReSpeaker3000"
    assert captured["suppression_enabled"] is True
    assert captured["suppression_doa_deg"] == 30.0
    assert result["mode"] == "own_voice_suppression"
    assert result["processed_audio"].shape[0] == mix_mc.shape[0]
    assert "sii_processed" in result["metrics"]


def test_compute_metrics_aligns_delayed_estimates() -> None:
    ref = np.zeros((800,), dtype=np.float32)
    ref[120:280] = 0.5
    delayed = np.pad(ref[:-40], (40, 0))
    metrics = validation_common.compute_metrics(ref, delayed, delayed, sample_rate_hz=16000)
    assert metrics["raw_lag_samples"] == 40
    assert metrics["processed_lag_samples"] == 40
    assert metrics["snr_raw"] > 40.0
    assert metrics["sii_raw"] > 0.85


def test_evaluate_mode_passthrough_returns_raw_mono(tmp_path: Path) -> None:
    speaker_dir = _write_recording(tmp_path / "speakers", recording_id="speaker-003", distance_m=1.5, direction_deg=15.0)
    noise_dir = _write_recording(tmp_path / "noise", recording_id="noise-003", distance_m=None, direction_deg=0.0)
    speaker_recording = validation_common.load_recording(speaker_dir)
    noise_recording = validation_common.load_recording(noise_dir)
    speaker_mc, noise_mc = validation_common.align_recordings(speaker_recording, noise_recording)
    channel_map = validation_common.active_channel_map_for_recording(speaker_recording)
    mix_mc = validation_common.mix_speaker_and_noise(speaker_mc, noise_mc, channel_map=channel_map)
    clean_ref_mono = validation_common.reference_mono_from_speaker(speaker_mc, channel_map=channel_map)

    result = validation_common.evaluate_mode(
        mix_mc=mix_mc,
        clean_ref_mono=clean_ref_mono,
        speaker_recording=speaker_recording,
        mode="amplification",
        suppression_enabled=False,
        suppression_doa_deg=None,
        processing_mode="passthrough",
    )

    expected_raw = validation_common.degraded_raw_mono_from_mix(mix_mc, channel_map=channel_map)
    assert np.allclose(result["processed_audio"], expected_raw)
    assert abs(float(result["metrics"]["snr_delta"])) < 1e-6
    assert abs(float(result["metrics"]["sii_delta"])) < 1e-6


def test_evaluate_mode_can_rms_match_processed_output_to_input(tmp_path: Path) -> None:
    speaker_dir = _write_recording(tmp_path / "speakers", recording_id="speaker-003b", distance_m=1.5, direction_deg=15.0)
    noise_dir = _write_recording(tmp_path / "noise", recording_id="noise-003b", distance_m=None, direction_deg=0.0)
    speaker_recording = validation_common.load_recording(speaker_dir)
    noise_recording = validation_common.load_recording(noise_dir)
    speaker_mc, noise_mc = validation_common.align_recordings(speaker_recording, noise_recording)
    channel_map = validation_common.active_channel_map_for_recording(speaker_recording)
    mix_mc = validation_common.mix_speaker_and_noise(speaker_mc, noise_mc, channel_map=channel_map)
    clean_ref_mono = validation_common.reference_mono_from_speaker(speaker_mc, channel_map=channel_map)

    result = validation_common.evaluate_mode(
        mix_mc=mix_mc,
        clean_ref_mono=clean_ref_mono,
        speaker_recording=speaker_recording,
        mode="amplification",
        suppression_enabled=False,
        suppression_doa_deg=None,
        processing_mode="passthrough",
        output_rms_match_input=True,
    )

    raw_mono = validation_common.degraded_raw_mono_from_mix(mix_mc, channel_map=channel_map)
    raw_rms = float(np.sqrt(np.mean(raw_mono**2)))
    proc_rms = float(np.sqrt(np.mean(np.asarray(result["processed_audio"], dtype=np.float32) ** 2)))
    assert abs(proc_rms - raw_rms) < 1e-6
    assert result["output_rms_match_input"] is True


def test_evaluate_mode_callback_uses_live_callback(monkeypatch, tmp_path: Path) -> None:
    speaker_dir = _write_recording(tmp_path / "speakers", recording_id="speaker-004", distance_m=1.5, direction_deg=15.0, samples=400)
    noise_dir = _write_recording(tmp_path / "noise", recording_id="noise-004", distance_m=None, direction_deg=0.0, samples=400)
    speaker_recording = validation_common.load_recording(speaker_dir)
    noise_recording = validation_common.load_recording(noise_dir)
    speaker_mc, noise_mc = validation_common.align_recordings(speaker_recording, noise_recording)
    channel_map = validation_common.active_channel_map_for_recording(speaker_recording)
    mix_mc = validation_common.mix_speaker_and_noise(speaker_mc, noise_mc, channel_map=channel_map)
    clean_ref_mono = validation_common.reference_mono_from_speaker(speaker_mc, channel_map=channel_map)

    calls: list[tuple[int, int, bool]] = []

    def fake_reset() -> None:
        return None

    def fake_callback(audio_bytes: bytes, channels: int, normalize_rms: bool = False) -> bytes:
        calls.append((len(audio_bytes), channels, normalize_rms))
        frame_samples = len(audio_bytes) // 2 // channels
        out = np.full((frame_samples,), 1234, dtype=np.int16)
        return out.tobytes()

    monkeypatch.setattr(validation_common, "_reset_processor_for_tests", fake_reset)
    monkeypatch.setattr(validation_common, "process_audio_callback", fake_callback)

    result = validation_common.evaluate_mode(
        mix_mc=mix_mc,
        clean_ref_mono=clean_ref_mono,
        speaker_recording=speaker_recording,
        mode="amplification",
        suppression_enabled=False,
        suppression_doa_deg=None,
        processing_mode="callback",
    )

    assert len(calls) == 3
    assert all(channels == 6 for _, channels, _ in calls)
    assert all(normalize_rms is False for _, _, normalize_rms in calls)
    expected = np.full((mix_mc.shape[0],), 1234 / 32767.0, dtype=np.float32)
    assert np.allclose(result["processed_audio"], expected)


def test_evaluate_mode_entrypoint_uses_root_audio_callback(monkeypatch, tmp_path: Path) -> None:
    speaker_dir = _write_recording(tmp_path / "speakers", recording_id="speaker-005", distance_m=1.5, direction_deg=15.0, samples=400)
    noise_dir = _write_recording(tmp_path / "noise", recording_id="noise-005", distance_m=None, direction_deg=0.0, samples=400)
    speaker_recording = validation_common.load_recording(speaker_dir)
    noise_recording = validation_common.load_recording(noise_dir)
    speaker_mc, noise_mc = validation_common.align_recordings(speaker_recording, noise_recording)
    channel_map = validation_common.active_channel_map_for_recording(speaker_recording)
    mix_mc = validation_common.mix_speaker_and_noise(speaker_mc, noise_mc, channel_map=channel_map)
    clean_ref_mono = validation_common.reference_mono_from_speaker(speaker_mc, channel_map=channel_map)

    calls: list[tuple[int, int]] = []

    def fake_entrypoint(audio_bytes: bytes, channels: int) -> bytes:
        calls.append((len(audio_bytes), channels))
        frame_samples = len(audio_bytes) // 2 // channels
        out = np.full((frame_samples,), -2345, dtype=np.int16)
        return out.tobytes()

    monkeypatch.setattr(validation_common, "_load_root_audio_callback", lambda: fake_entrypoint)
    monkeypatch.setattr(validation_common, "_reset_processor_for_tests", lambda: None)

    result = validation_common.evaluate_mode(
        mix_mc=mix_mc,
        clean_ref_mono=clean_ref_mono,
        speaker_recording=speaker_recording,
        mode="amplification",
        suppression_enabled=False,
        suppression_doa_deg=None,
        processing_mode="entrypoint",
    )

    assert len(calls) == 3
    assert all(channels == 6 for _, channels in calls)
    expected = np.full((mix_mc.shape[0],), -2345 / 32767.0, dtype=np.float32)
    assert np.allclose(result["processed_audio"], expected)


def test_evaluate_mode_research_adapter_uses_research_runner(monkeypatch, tmp_path: Path) -> None:
    speaker_dir = _write_recording(tmp_path / "speakers", recording_id="speaker-006", distance_m=1.5, direction_deg=25.0)
    noise_dir = _write_recording(tmp_path / "noise", recording_id="noise-006", distance_m=None, direction_deg=0.0)
    speaker_recording = validation_common.load_recording(speaker_dir)
    noise_recording = validation_common.load_recording(noise_dir)
    speaker_mc, noise_mc = validation_common.align_recordings(speaker_recording, noise_recording)
    channel_map = validation_common.active_channel_map_for_recording(speaker_recording)
    mix_mc = validation_common.mix_speaker_and_noise(speaker_mc, noise_mc, channel_map=channel_map)
    clean_ref_mono = validation_common.reference_mono_from_speaker(speaker_mc, channel_map=channel_map)

    captured = {}

    def fake_research_runner(audio_mc, *, mic_profile_name, own_voice_suppression_enabled, own_voice_suppression_doa_deg):
        captured["shape"] = tuple(audio_mc.shape)
        captured["mic_profile_name"] = mic_profile_name
        captured["suppression_enabled"] = own_voice_suppression_enabled
        captured["suppression_doa_deg"] = own_voice_suppression_doa_deg
        return np.mean(audio_mc[:, [1, 2, 3, 4]], axis=1).astype(np.float32)

    monkeypatch.setattr(validation_common, "run_research_adapter_pipeline", fake_research_runner)

    result = validation_common.evaluate_mode(
        mix_mc=mix_mc,
        clean_ref_mono=clean_ref_mono,
        speaker_recording=speaker_recording,
        mode="own_voice_suppression",
        suppression_enabled=True,
        suppression_doa_deg=25.0,
        processing_mode="research_adapter",
    )

    assert captured["shape"] == tuple(mix_mc.shape)
    assert captured["mic_profile_name"] == "ReSpeaker3000"
    assert captured["suppression_enabled"] is True
    assert captured["suppression_doa_deg"] == 25.0
    assert result["processing_mode"] == "research_adapter"


def test_run_research_adapter_pipeline_uses_respeaker3000_active_channels_and_params(monkeypatch) -> None:
    calls = {}

    class FakeAdapter:
        def __init__(self, **kwargs):
            calls["init_kwargs"] = kwargs
            calls["process_shapes"] = []
            calls["process_dtypes"] = []
            calls["closed"] = False

        def process_chunk(self, channels):
            calls["process_shapes"].append(tuple(np.asarray(ch).shape[0] for ch in channels))
            calls["process_dtypes"].append(tuple(np.asarray(ch).dtype for ch in channels))
            frame_len = int(np.asarray(channels[0]).shape[0])
            return np.full((frame_len,), 1111 / 32767.0, dtype=np.float32)

        def close(self):
            calls["closed"] = True

    monkeypatch.setattr(validation_common, "_load_research_adapter_class", lambda: FakeAdapter)

    audio_mc = np.zeros((400, 6), dtype=np.float32)
    audio_mc[:, 1] = 0.1
    audio_mc[:, 2] = 0.2
    audio_mc[:, 3] = 0.3
    audio_mc[:, 4] = 0.4

    out = validation_common.run_research_adapter_pipeline(
        audio_mc,
        mic_profile_name="ReSpeaker3000",
        own_voice_suppression_enabled=True,
        own_voice_suppression_doa_deg=335.0,
    )

    assert out.shape == (400,)
    assert len(calls["process_shapes"]) == 3
    assert all(shape == (160, 160, 160, 160) for shape in calls["process_shapes"])
    assert all(all(dtype == np.int16 for dtype in dtypes) for dtypes in calls["process_dtypes"])
    assert calls["init_kwargs"]["mic_array_profile"] == "respeaker_v3_0457"
    assert calls["init_kwargs"]["input_sample_rate_hz"] == 16000
    assert calls["init_kwargs"]["processing_sample_rate_hz"] == 16000
    assert calls["init_kwargs"]["enable_resample"] is False
    assert calls["init_kwargs"]["beamforming_mode"] == "delay_sum"
    assert calls["init_kwargs"]["postfilter_method"] == "rnnoise"
    assert calls["init_kwargs"]["localization_backend"] == "capon_1src"
    assert calls["init_kwargs"]["localization_vad_enabled"] is False
    assert calls["init_kwargs"]["own_voice_suppression_enabled"] is True
    assert calls["init_kwargs"]["own_voice_suppression_doa_deg"] == 335.0
    assert np.asarray(calls["init_kwargs"]["mic_geometry_xyz"]).shape == (4, 3)
    assert calls["closed"] is True
