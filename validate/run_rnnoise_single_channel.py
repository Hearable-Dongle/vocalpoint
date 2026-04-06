from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_RNNOISE_SAMPLE_RATE_HZ = 48000

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from validate.common import (
        _INPUT_SAMPLE_RATE_HZ,
        _load_wav,
        compute_metrics,
        maybe_resample_audio,
        run_rnnoise_mono_audio,
        save_wav,
    )
else:  # pragma: no cover
    from validate.common import (
        _INPUT_SAMPLE_RATE_HZ,
        _load_wav,
        compute_metrics,
        maybe_resample_audio,
        run_rnnoise_mono_audio,
        save_wav,
    )

def _load_mono_float32(path: str | Path, *, output_rate_hz: int) -> np.ndarray:
    sample_rate_hz, audio = _load_wav(Path(path))
    return np.asarray(
        maybe_resample_audio(
            audio.astype(np.float32) / 32768.0,
            input_rate_hz=int(sample_rate_hz),
            output_rate_hz=int(output_rate_hz),
        ),
        dtype=np.float32,
    ).reshape(-1)


def _write_waveform_plot(
    path: Path,
    *,
    sample_rate_hz: int,
    title: str,
    audio_series: list[tuple[str, np.ndarray]],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(len(audio_series), 1, figsize=(12, max(3, 2.5 * len(audio_series))), sharex=True)
    axes_arr = np.atleast_1d(axes)

    for ax, (label, audio) in zip(axes_arr, audio_series, strict=False):
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        time_sec = np.arange(samples.shape[0], dtype=np.float32) / float(sample_rate_hz)
        ax.plot(time_sec, samples, linewidth=0.6)
        ax.set_ylabel(label)
        ax.set_ylim(-1.05, 1.05)
        ax.grid(True, alpha=0.3)

    axes_arr[-1].set_xlabel("Time (s)")
    fig.suptitle(title)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RNNoise only on one mono channel and report SII/SNR.")
    parser.add_argument("--clean-ref", required=True, help="Path to clean mono reference WAV.")
    parser.add_argument("--noisy-input", required=True, help="Path to noisy mono input WAV.")
    parser.add_argument(
        "--output-dir",
        default=str(Path("validate") / "outputs" / "rnnoise_single_channel_debug"),
        help="Directory for denoised waveform and metrics JSON. Default: validate/outputs/rnnoise_single_channel_debug",
    )
    args = parser.parse_args()

    clean_ref = _load_mono_float32(args.clean_ref, output_rate_hz=_RNNOISE_SAMPLE_RATE_HZ)
    noisy_input = _load_mono_float32(args.noisy_input, output_rate_hz=_RNNOISE_SAMPLE_RATE_HZ)
    sample_count = min(int(clean_ref.shape[0]), int(noisy_input.shape[0]))
    if sample_count <= 0:
        raise ValueError("clean-ref and noisy-input must both contain audio")
    clean_ref = clean_ref[:sample_count]
    noisy_input = noisy_input[:sample_count]
    denoised = run_rnnoise_mono_audio(noisy_input, sample_rate_hz=_RNNOISE_SAMPLE_RATE_HZ)
    denoised = np.asarray(denoised[:sample_count], dtype=np.float32)

    metrics = compute_metrics(
        clean_ref_mono=clean_ref,
        degraded_raw_mono=noisy_input,
        processed_mono=denoised,
        sample_rate_hz=_RNNOISE_SAMPLE_RATE_HZ,
    )

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    save_wav(output_dir / "clean_ref.wav", clean_ref, sample_rate_hz=_RNNOISE_SAMPLE_RATE_HZ)
    save_wav(output_dir / "noisy_input.wav", noisy_input, sample_rate_hz=_RNNOISE_SAMPLE_RATE_HZ)
    save_wav(output_dir / "denoised.wav", denoised, sample_rate_hz=_RNNOISE_SAMPLE_RATE_HZ)
    _write_waveform_plot(
        output_dir / "waveforms.png",
        sample_rate_hz=_RNNOISE_SAMPLE_RATE_HZ,
        title="RNNoise Single-Channel Debug Waveforms",
        audio_series=[
            ("clean_ref", clean_ref),
            ("noisy_input", noisy_input),
            ("denoised", denoised),
        ],
    )
    summary = {
        "clean_ref": str(Path(args.clean_ref).resolve()),
        "noisy_input": str(Path(args.noisy_input).resolve()),
        "sample_rate_hz": int(_RNNOISE_SAMPLE_RATE_HZ),
        **metrics,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), **summary}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
