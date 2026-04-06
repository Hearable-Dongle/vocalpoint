from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly


REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNAL_PROCESSING_RESEARCH_ROOT = REPO_ROOT / "signal-processing-research"
if str(SIGNAL_PROCESSING_RESEARCH_ROOT) not in sys.path:
    sys.path.insert(0, str(SIGNAL_PROCESSING_RESEARCH_ROOT))

from beamforming.util.compare import calc_snr  # noqa: E402
from verification.sii_utils import compute_sii  # noqa: E402
from rpi.process_audio import (  # noqa: E402
    _INPUT_SAMPLE_RATE_HZ,
    _RESPEAKER3000_PROFILE_NAME,
    process_multichannel_audio,
)


VALIDATE_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = VALIDATE_ROOT / "outputs"
AMPLIFICATION_OUTPUT_ROOT = OUTPUT_ROOT / "amplification"
SUPPRESSION_OUTPUT_ROOT = OUTPUT_ROOT / "own_voice_suppression"


@dataclass(frozen=True, slots=True)
class RecordingData:
    recording_dir: Path
    recording_id: str
    sample_rate_hz: int
    mic_array_profile: str
    channels: tuple[np.ndarray, ...]
    metadata: dict[str, Any]


def generate_white_noise_like(
    reference_mc: np.ndarray,
    *,
    seed: int = 0,
    amplitude: float = 0.25,
) -> np.ndarray:
    ref = np.asarray(reference_mc, dtype=np.float32)
    if ref.ndim != 2:
        raise ValueError("reference_mc must be shape (samples, channels)")
    rng = np.random.default_rng(int(seed))
    noise = (float(amplitude) * rng.standard_normal(size=ref.shape)).astype(np.float32)
    return np.asarray(noise, dtype=np.float32)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_wav(path: Path) -> tuple[int, np.ndarray]:
    sample_rate_hz, audio = wavfile.read(path)
    if audio.ndim == 1:
        return int(sample_rate_hz), np.asarray(audio, dtype=np.int16)
    if audio.ndim == 2 and audio.shape[1] == 1:
        return int(sample_rate_hz), np.asarray(audio[:, 0], dtype=np.int16)
    raise ValueError(f"expected mono WAV at {path}, got shape {audio.shape}")


def load_recording(recording_dir: str | Path) -> RecordingData:
    base = Path(recording_dir).resolve()
    metadata_path = base / "metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"missing metadata.json in {base}")
    metadata = _read_json(metadata_path)
    artifacts = dict(metadata.get("artifacts", {}))
    channels_meta = list(artifacts.get("channels", []))
    if not channels_meta:
        raise ValueError(f"no channel artifacts declared in {metadata_path}")
    loaded_channels: list[np.ndarray] = []
    sample_rate_hz: int | None = None
    for channel_meta in channels_meta:
        filename = str(channel_meta["filename"])
        wav_path = base / "raw" / filename
        sr, audio = _load_wav(wav_path)
        if sample_rate_hz is None:
            sample_rate_hz = int(sr)
        elif int(sr) != int(sample_rate_hz):
            raise ValueError(f"mismatched sample rates in {base}")
        loaded_channels.append(np.asarray(audio, dtype=np.int16))
    lengths = {int(channel.shape[0]) for channel in loaded_channels}
    if len(lengths) != 1:
        raise ValueError(f"channel lengths differ in {base}")
    return RecordingData(
        recording_dir=base,
        recording_id=str(metadata.get("recordingId") or base.name),
        sample_rate_hz=int(sample_rate_hz if sample_rate_hz is not None else artifacts.get("sampleRateHz", _INPUT_SAMPLE_RATE_HZ)),
        mic_array_profile=str(metadata.get("micArrayProfile") or _RESPEAKER3000_PROFILE_NAME),
        channels=tuple(loaded_channels),
        metadata=metadata,
    )


def recording_distance_m(recording: RecordingData) -> float | None:
    validation = dict(recording.metadata.get("validation", {}))
    value = validation.get("distanceM")
    return None if value is None else float(value)


def recording_direction_deg(recording: RecordingData) -> float:
    speakers = list(recording.metadata.get("speakers", []))
    if not speakers:
        return 0.0
    periods = list(dict(speakers[0]).get("speakingPeriods", []))
    if not periods:
        return 0.0
    return float(dict(periods[0]).get("directionDeg", 0.0))


def _to_float32(audio: np.ndarray) -> np.ndarray:
    arr = np.asarray(audio)
    if np.issubdtype(arr.dtype, np.integer):
        return (arr.astype(np.float32) / 32768.0).astype(np.float32, copy=False)
    return np.asarray(arr, dtype=np.float32)


def recording_to_multichannel_float32(recording: RecordingData) -> np.ndarray:
    return np.stack([_to_float32(channel) for channel in recording.channels], axis=1).astype(np.float32, copy=False)


def maybe_resample_audio(audio: np.ndarray, *, input_rate_hz: int, output_rate_hz: int) -> np.ndarray:
    if int(input_rate_hz) == int(output_rate_hz):
        return np.asarray(audio, dtype=np.float32)
    return np.asarray(
        resample_poly(np.asarray(audio, dtype=np.float32), up=int(output_rate_hz), down=int(input_rate_hz), axis=0),
        dtype=np.float32,
    )


def align_recordings(
    speaker_recording: RecordingData,
    noise_recording: RecordingData,
    *,
    output_rate_hz: int = _INPUT_SAMPLE_RATE_HZ,
) -> tuple[np.ndarray, np.ndarray]:
    speaker_mc = maybe_resample_audio(
        recording_to_multichannel_float32(speaker_recording),
        input_rate_hz=int(speaker_recording.sample_rate_hz),
        output_rate_hz=int(output_rate_hz),
    )
    noise_mc = maybe_resample_audio(
        recording_to_multichannel_float32(noise_recording),
        input_rate_hz=int(noise_recording.sample_rate_hz),
        output_rate_hz=int(output_rate_hz),
    )
    if speaker_mc.shape[1] != noise_mc.shape[1]:
        raise ValueError("speaker and noise channel counts do not match")
    sample_count = min(int(speaker_mc.shape[0]), int(noise_mc.shape[0]))
    if sample_count <= 0:
        raise ValueError("speaker/noise recordings are empty after alignment")
    return speaker_mc[:sample_count, :], noise_mc[:sample_count, :]


def rms_match_noise_to_speaker(speaker_mc: np.ndarray, noise_mc: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    speaker_rms = float(np.sqrt(np.mean(np.asarray(speaker_mc, dtype=np.float64) ** 2) + eps))
    noise_rms = float(np.sqrt(np.mean(np.asarray(noise_mc, dtype=np.float64) ** 2) + eps))
    if noise_rms <= eps:
        return np.zeros_like(noise_mc, dtype=np.float32)
    scale = speaker_rms / noise_rms
    return np.asarray(noise_mc * scale, dtype=np.float32)


def mix_speaker_and_noise(speaker_mc: np.ndarray, noise_mc: np.ndarray) -> np.ndarray:
    matched_noise = rms_match_noise_to_speaker(speaker_mc, noise_mc)
    return np.asarray(0.5 * (speaker_mc + matched_noise), dtype=np.float32)


def reference_mono_from_speaker(speaker_mc: np.ndarray) -> np.ndarray:
    return np.mean(np.asarray(speaker_mc, dtype=np.float32), axis=1).astype(np.float32, copy=False)


def degraded_raw_mono_from_mix(mix_mc: np.ndarray) -> np.ndarray:
    return np.mean(np.asarray(mix_mc, dtype=np.float32), axis=1).astype(np.float32, copy=False)


def save_wav(path: Path, audio: np.ndarray, *, sample_rate_hz: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(audio)
    if arr.ndim == 1:
        pcm = np.clip(arr, -1.0, 1.0)
        wavfile.write(path, int(sample_rate_hz), np.asarray(np.round(pcm * 32767.0), dtype=np.int16))
        return
    pcm = np.clip(arr, -1.0, 1.0)
    wavfile.write(path, int(sample_rate_hz), np.asarray(np.round(pcm * 32767.0), dtype=np.int16))


def compute_metrics(clean_ref_mono: np.ndarray, degraded_raw_mono: np.ndarray, processed_mono: np.ndarray, *, sample_rate_hz: int) -> dict[str, float]:
    ref = np.asarray(clean_ref_mono, dtype=np.float32).reshape(-1)
    raw = np.asarray(degraded_raw_mono, dtype=np.float32).reshape(-1)
    proc = np.asarray(processed_mono, dtype=np.float32).reshape(-1)
    sample_count = min(ref.shape[0], raw.shape[0], proc.shape[0])
    ref = ref[:sample_count]
    raw = raw[:sample_count]
    proc = proc[:sample_count]
    return {
        "snr_raw": float(calc_snr(ref, raw)),
        "snr_processed": float(calc_snr(ref, proc)),
        "snr_delta": float(calc_snr(ref, proc) - calc_snr(ref, raw)),
        "sii_raw": float(compute_sii(ref, raw, int(sample_rate_hz))),
        "sii_processed": float(compute_sii(ref, proc, int(sample_rate_hz))),
        "sii_delta": float(compute_sii(ref, proc, int(sample_rate_hz)) - compute_sii(ref, raw, int(sample_rate_hz))),
    }


def evaluate_mode(
    *,
    mix_mc: np.ndarray,
    clean_ref_mono: np.ndarray,
    speaker_recording: RecordingData,
    mode: str,
    suppression_enabled: bool,
    suppression_doa_deg: float | None,
) -> dict[str, Any]:
    processed = process_multichannel_audio(
        mix_mc,
        sample_rate_hz=_INPUT_SAMPLE_RATE_HZ,
        mic_profile_name=str(speaker_recording.mic_array_profile),
        own_voice_suppression_enabled=bool(suppression_enabled),
        own_voice_suppression_doa_deg=suppression_doa_deg,
    )
    raw_mono = degraded_raw_mono_from_mix(mix_mc)
    metrics = compute_metrics(clean_ref_mono, raw_mono, processed, sample_rate_hz=_INPUT_SAMPLE_RATE_HZ)
    return {
        "mode": str(mode),
        "processed_audio": np.asarray(processed, dtype=np.float32),
        "raw_mono": np.asarray(raw_mono, dtype=np.float32),
        "metrics": metrics,
    }


def save_mode_outputs(
    *,
    output_root: Path,
    identifier: str,
    mix_mc: np.ndarray,
    clean_ref_mono: np.ndarray,
    noise_mc: np.ndarray,
    result: dict[str, Any],
    speaker_recording: RecordingData,
    noise_recording: RecordingData,
) -> Path:
    out_dir = output_root / identifier
    out_dir.mkdir(parents=True, exist_ok=True)
    save_wav(out_dir / "speaker_reference_mono.wav", clean_ref_mono, sample_rate_hz=_INPUT_SAMPLE_RATE_HZ)
    save_wav(out_dir / "noise_multichannel.wav", noise_mc, sample_rate_hz=_INPUT_SAMPLE_RATE_HZ)
    save_wav(out_dir / "mixture_multichannel.wav", mix_mc, sample_rate_hz=_INPUT_SAMPLE_RATE_HZ)
    save_wav(out_dir / "mixture_raw_mono.wav", result["raw_mono"], sample_rate_hz=_INPUT_SAMPLE_RATE_HZ)
    save_wav(out_dir / "processed_mono.wav", result["processed_audio"], sample_rate_hz=_INPUT_SAMPLE_RATE_HZ)
    summary = {
        "identifier": str(identifier),
        "mode": str(result["mode"]),
        "speaker_recording_id": str(speaker_recording.recording_id),
        "noise_recording_id": str(noise_recording.recording_id),
        "speaker_direction_deg": float(recording_direction_deg(speaker_recording)),
        "distance_m": recording_distance_m(speaker_recording),
        **dict(result["metrics"]),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_dir


def identifier_for_recording(recording: RecordingData) -> str:
    return str(recording.recording_id or recording.recording_dir.name)


def discover_recording_dirs(root_dir: str | Path) -> list[Path]:
    root = Path(root_dir).resolve()
    if (root / "metadata.json").is_file():
        return [root]
    return sorted(path.parent for path in root.rglob("metadata.json"))


def aggregate_results_by_distance(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[float, list[dict[str, Any]]] = {}
    for row in rows:
        distance = row.get("distance_m")
        if distance is None:
            continue
        grouped.setdefault(float(distance), []).append(row)
    summary: list[dict[str, Any]] = []
    for distance, items in sorted(grouped.items()):
        sii_vals = np.asarray([float(item["sii_processed"]) for item in items], dtype=np.float64)
        snr_vals = np.asarray([float(item["snr_processed"]) for item in items], dtype=np.float64)
        summary.append(
            {
                "distance_m": float(distance),
                "count": int(len(items)),
                "sii_mean": float(np.mean(sii_vals)),
                "sii_median": float(np.median(sii_vals)),
                "sii_std": float(np.std(sii_vals)),
                "snr_mean": float(np.mean(snr_vals)),
                "snr_median": float(np.median(snr_vals)),
                "snr_std": float(np.std(snr_vals)),
            }
        )
    return summary
