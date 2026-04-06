from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from pyrnnoise import RNNoise

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from validate.common import (
        _INPUT_SAMPLE_RATE_HZ,
        _load_wav,
        compute_metrics,
        maybe_resample_audio,
        save_wav,
    )
    from validate.run_rnnoise_single_channel import _write_waveform_plot
else:  # pragma: no cover
    from validate.common import (
        _INPUT_SAMPLE_RATE_HZ,
        _load_wav,
        compute_metrics,
        maybe_resample_audio,
        save_wav,
    )
    from validate.run_rnnoise_single_channel import _write_waveform_plot


def _load_mono_float32(path: str | Path, *, output_rate_hz: int) -> np.ndarray:
    sample_rate_hz, audio = _load_wav(Path(path))
    return np.asarray(
        maybe_resample_audio(audio.astype(np.float32) / 32768.0, input_rate_hz=int(sample_rate_hz), output_rate_hz=int(output_rate_hz)),
        dtype=np.float32,
    ).reshape(-1)


def run_pyrnnoise_raw(audio: np.ndarray, *, sample_rate_hz: int) -> np.ndarray:
    if int(sample_rate_hz) != 16000:
        raise ValueError(f"pyrnnoise raw runner expects 16000 Hz, got {sample_rate_hz}")
    backend = RNNoise(int(sample_rate_hz))
    backend.channels = 1
    backend.dtype = np.int16

    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    frame_size = 160
    outputs: list[np.ndarray] = []
    for start in range(0, int(x.shape[0]), frame_size):
        chunk = x[start : start + frame_size]
        original_len = int(chunk.shape[0])
        if original_len < frame_size:
            chunk = np.pad(chunk, (0, frame_size - original_len))
        chunk_i16 = np.clip(np.round(chunk * 32768.0), -32768.0, 32767.0).astype(np.int16, copy=False)
        chunk_out_parts: list[np.ndarray] = []
        for _vad_prob, den in backend.denoise_chunk(np.atleast_2d(chunk_i16), partial=False):
            den_arr = np.asarray(den, dtype=np.float32).reshape(-1)
            if den_arr.dtype.kind in {"i", "u"} or float(np.max(np.abs(den_arr))) > 1.5:
                den_arr = den_arr / 32768.0
            chunk_out_parts.append(np.asarray(den_arr, dtype=np.float32))
        if chunk_out_parts:
            chunk_out = np.concatenate(chunk_out_parts, axis=0)
        else:
            chunk_out = np.zeros((frame_size,), dtype=np.float32)
        outputs.append(np.asarray(chunk_out[:original_len], dtype=np.float32))
    if not outputs:
        return np.zeros((0,), dtype=np.float32)
    return np.concatenate(outputs, axis=0).astype(np.float32, copy=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run raw pyrnnoise.RNNoise on one mono channel and report SII/SNR.")
    parser.add_argument("--clean-ref", required=True, help="Path to clean mono reference WAV.")
    parser.add_argument("--noisy-input", required=True, help="Path to noisy mono input WAV.")
    parser.add_argument(
        "--output-dir",
        default=str(Path("validate") / "outputs" / "pyrnnoise_raw_debug"),
        help="Directory for denoised waveform, waveform plot, and metrics JSON.",
    )
    args = parser.parse_args()

    clean_ref = _load_mono_float32(args.clean_ref, output_rate_hz=_INPUT_SAMPLE_RATE_HZ)
    noisy_input = _load_mono_float32(args.noisy_input, output_rate_hz=_INPUT_SAMPLE_RATE_HZ)
    sample_count = min(int(clean_ref.shape[0]), int(noisy_input.shape[0]))
    if sample_count <= 0:
        raise ValueError("clean-ref and noisy-input must both contain audio")
    clean_ref = clean_ref[:sample_count]
    noisy_input = noisy_input[:sample_count]

    denoised = run_pyrnnoise_raw(noisy_input, sample_rate_hz=_INPUT_SAMPLE_RATE_HZ)
    denoised = np.asarray(denoised[:sample_count], dtype=np.float32)

    metrics = compute_metrics(
        clean_ref_mono=clean_ref,
        degraded_raw_mono=noisy_input,
        processed_mono=denoised,
        sample_rate_hz=_INPUT_SAMPLE_RATE_HZ,
    )

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    save_wav(output_dir / "clean_ref.wav", clean_ref, sample_rate_hz=_INPUT_SAMPLE_RATE_HZ)
    save_wav(output_dir / "noisy_input.wav", noisy_input, sample_rate_hz=_INPUT_SAMPLE_RATE_HZ)
    save_wav(output_dir / "denoised.wav", denoised, sample_rate_hz=_INPUT_SAMPLE_RATE_HZ)
    _write_waveform_plot(
        output_dir / "waveforms.png",
        sample_rate_hz=_INPUT_SAMPLE_RATE_HZ,
        title="Raw pyrnnoise Debug Waveforms",
        audio_series=[
            ("clean_ref", clean_ref),
            ("noisy_input", noisy_input),
            ("denoised", denoised),
        ],
    )
    summary = {
        "backend": "pyrnnoise.RNNoise",
        "clean_ref": str(Path(args.clean_ref).resolve()),
        "noisy_input": str(Path(args.noisy_input).resolve()),
        "sample_rate_hz": int(_INPUT_SAMPLE_RATE_HZ),
        **metrics,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), **summary}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
