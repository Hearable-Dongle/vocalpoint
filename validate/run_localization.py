from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from validate.common import (
        VALIDATE_ROOT,
        active_channel_map_for_recording,
        align_recordings,
        generate_white_noise_like,
        get_mic_profile,
        identifier_for_recording,
        load_recording,
        mix_speaker_and_noise,
        recording_direction_deg,
        save_wav,
    )
    from rpi.localization import CaponLocalization, SRPPHATLocalizer, _gcc_phat
else:  # pragma: no cover
    from validate.common import (
        VALIDATE_ROOT,
        active_channel_map_for_recording,
        align_recordings,
        generate_white_noise_like,
        get_mic_profile,
        identifier_for_recording,
        load_recording,
        mix_speaker_and_noise,
        recording_direction_deg,
        save_wav,
    )
    from rpi.localization import CaponLocalization, SRPPHATLocalizer, _gcc_phat


_OUTPUT_ROOT = VALIDATE_ROOT / "outputs" / "localization"
_WINDOW_MS = 200
_WINDOW_SAMPLES = 3200


def _circular_error_deg(predicted_deg: float, target_deg: float) -> float:
    delta = abs((float(predicted_deg) % 360.0) - (float(target_deg) % 360.0))
    return float(min(delta, 360.0 - delta))


def _write_prediction_plot(
    path: Path,
    *,
    times_sec: np.ndarray,
    predicted_deg: np.ndarray,
    error_deg: np.ndarray,
    target_deg: float,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    axes[0].plot(times_sec, predicted_deg, linewidth=1.0, label="predicted_doa_deg")
    axes[0].axhline(float(target_deg), color="tab:red", linestyle="--", linewidth=1.0, label="ground_truth_doa_deg")
    axes[0].set_ylabel("DOA (deg)")
    axes[0].set_ylim(-5.0, 365.0)
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc="upper right")

    axes[1].plot(times_sec, error_deg, linewidth=1.0, color="tab:orange", label="absolute_error_deg")
    axes[1].set_ylabel("Error (deg)")
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylim(bottom=0.0)
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc="upper right")

    fig.suptitle("Localization Predictions Over Time")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _write_average_spectrum_histogram(
    path: Path,
    *,
    doa_deg: np.ndarray,
    average_spectrum: np.ndarray,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 4.5))
    width = float(360.0 / max(1, doa_deg.size))
    ax.bar(doa_deg, average_spectrum, width=width, align="edge", color="tab:blue", alpha=0.85)
    ax.set_xlim(0.0, 360.0)
    ax.set_xlabel("DOA Bin (deg)")
    ax.set_ylabel("Average Spectrum")
    ax.set_title("Average Spectrum by DOA Bin")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _write_gcc_phat_pair_plot(
    path: Path,
    *,
    pair_rows: list[dict[str, object]],
    sample_rate_hz: int,
    window_start_sec: float,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not pair_rows:
        return

    fig, axes = plt.subplots(len(pair_rows), 1, figsize=(12, 2.6 * len(pair_rows)), sharex=True)
    if not isinstance(axes, np.ndarray):
        axes = np.asarray([axes], dtype=object)

    for ax, row in zip(axes.tolist(), pair_rows, strict=False):
        lag_samples = np.asarray(row["lag_samples"], dtype=np.float64)
        corr = np.asarray(row["corr"], dtype=np.float64)
        peak_lag = float(row["peak_lag_samples"])
        peak_val = float(row["peak_value"])
        pair_label = str(row["pair_label"])
        ax.plot(lag_samples / float(sample_rate_hz) * 1000.0, corr, linewidth=1.0)
        ax.axvline(peak_lag / float(sample_rate_hz) * 1000.0, color="tab:red", linestyle="--", linewidth=1.0)
        ax.scatter([peak_lag / float(sample_rate_hz) * 1000.0], [peak_val], color="tab:red", s=20, zorder=3)
        ax.set_ylabel(pair_label)
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("Lag (ms)")
    fig.suptitle(f"GCC-PHAT per mic pair, strongest 200 ms window at {window_start_sec:.2f}s")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate DOA localization on ReSpeaker3000 recordings.")
    parser.add_argument("--speaker-dir", required=True, help="Path to one collected speaker recording directory.")
    parser.add_argument("--noise-dir", help="Path to one collected noise recording directory.")
    parser.add_argument(
        "--noise-mode",
        choices=("recorded", "white"),
        default="recorded",
        help="Noise source to mix with the speaker recording. Default: recorded.",
    )
    parser.add_argument(
        "--noise-scale",
        type=float,
        default=1.0,
        help="Multiplier applied to RMS-matched noise before averaging with the speaker signal. Default: 1.0.",
    )
    parser.add_argument(
        "--output-dir",
        help="Optional explicit output directory. Default: validate/outputs/localization/<identifier>/",
    )
    parser.add_argument(
        "--method",
        choices=("capon", "srp_phat"),
        default="capon",
        help="Localization backend to evaluate. Default: capon.",
    )
    parser.add_argument(
        "--spectrum-ema-alpha",
        type=float,
        default=0.0,
        help="Spectrum EMA alpha passed to the localizer. Default: 0.0.",
    )
    args = parser.parse_args()

    speaker_recording = load_recording(args.speaker_dir)
    if args.noise_mode == "recorded":
        if not args.noise_dir:
            raise ValueError("--noise-dir is required when --noise-mode=recorded")
        noise_recording = load_recording(args.noise_dir)
        speaker_mc, noise_mc = align_recordings(speaker_recording, noise_recording)
    else:
        speaker_mc = align_recordings(speaker_recording, speaker_recording)[0]
        noise_mc = generate_white_noise_like(speaker_mc, seed=0)
        noise_recording = speaker_recording

    channel_map = active_channel_map_for_recording(speaker_recording)
    mix_mc = mix_speaker_and_noise(speaker_mc, noise_mc, channel_map=channel_map, noise_scale=float(args.noise_scale))
    active_mix = np.asarray(mix_mc[:, list(channel_map)], dtype=np.float32)
    profile = get_mic_profile(str(speaker_recording.mic_array_profile))
    mic_geometry_xyz = np.asarray(profile["mic_geometry_xyz"], dtype=np.float64)
    target_doa_deg = float(recording_direction_deg(speaker_recording))

    localizer_cls = CaponLocalization if str(args.method) == "capon" else SRPPHATLocalizer
    localizer = localizer_cls(
        mic_positions_xyz=mic_geometry_xyz,
        sample_rate_hz=int(speaker_recording.sample_rate_hz),
        grid_size=360,
        hold_frames=0,
        spectrum_ema_alpha=float(args.spectrum_ema_alpha),
        peak_min_sharpness=0.0,
        peak_min_margin=0.0,
        vad_enabled=False,
    )

    predictions: list[dict[str, float | int | bool | None]] = []
    spectrum_sum: np.ndarray | None = None
    spectrum_count = 0
    window_rms: list[float] = []
    for start in range(0, int(active_mix.shape[0]) - _WINDOW_SAMPLES + 1, _WINDOW_SAMPLES):
        window = active_mix[start : start + _WINDOW_SAMPLES, :]
        window_rms.append(float(np.sqrt(np.mean(np.asarray(window, dtype=np.float64) ** 2))))
        result = localizer.process(window)
        spectrum_arr = np.asarray(result.spectrum, dtype=np.float64).reshape(-1)
        if spectrum_arr.size > 0:
            if spectrum_sum is None or spectrum_sum.shape != spectrum_arr.shape:
                spectrum_sum = np.zeros_like(spectrum_arr, dtype=np.float64)
            spectrum_sum += spectrum_arr
            spectrum_count += 1
        predicted = None if result.doa_deg is None else float(result.doa_deg)
        error = None if predicted is None else _circular_error_deg(predicted, target_doa_deg)
        predictions.append(
            {
                "start_sample": int(start),
                "end_sample": int(start + _WINDOW_SAMPLES),
                "time_sec": float(start / float(speaker_recording.sample_rate_hz)),
                "predicted_doa_deg": predicted,
                "target_doa_deg": float(target_doa_deg),
                "absolute_error_deg": error,
                "confidence": float(result.confidence),
                "accepted": bool(result.accepted),
                "held": bool(result.held),
            }
        )

    valid_predictions = [row for row in predictions if row["predicted_doa_deg"] is not None]
    errors = np.asarray([float(row["absolute_error_deg"]) for row in valid_predictions], dtype=np.float64)
    identifier = identifier_for_recording(speaker_recording)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else (_OUTPUT_ROOT / identifier).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    save_wav(output_dir / "mixture_multichannel.wav", mix_mc, sample_rate_hz=int(speaker_recording.sample_rate_hz))
    if valid_predictions:
        times_sec = np.asarray([float(row["time_sec"]) for row in valid_predictions], dtype=np.float32)
        predicted_deg = np.asarray([float(row["predicted_doa_deg"]) for row in valid_predictions], dtype=np.float32)
        error_deg = np.asarray([float(row["absolute_error_deg"]) for row in valid_predictions], dtype=np.float32)
        _write_prediction_plot(
            output_dir / "predictions_over_time.png",
            times_sec=times_sec,
            predicted_deg=predicted_deg,
            error_deg=error_deg,
            target_deg=target_doa_deg,
        )
    average_spectrum = None
    if spectrum_sum is not None and spectrum_count > 0:
        average_spectrum = np.asarray(spectrum_sum / float(spectrum_count), dtype=np.float64)
        doa_bins_deg = np.linspace(0.0, 360.0, average_spectrum.size, endpoint=False, dtype=np.float64)
        _write_average_spectrum_histogram(
            output_dir / "average_spectrum_histogram.png",
            doa_deg=doa_bins_deg,
            average_spectrum=average_spectrum,
        )
        (output_dir / "average_spectrum_by_doa.json").write_text(
            json.dumps(
                [
                    {"doa_deg": float(doa_deg), "average_spectrum": float(value)}
                    for doa_deg, value in zip(doa_bins_deg.tolist(), average_spectrum.tolist(), strict=False)
                ],
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    if str(args.method) == "srp_phat" and predictions:
        strongest_idx = int(np.argmax(np.asarray(window_rms, dtype=np.float64)))
        strongest_start = strongest_idx * _WINDOW_SAMPLES
        strongest_window = active_mix[strongest_start : strongest_start + _WINDOW_SAMPLES, :]
        pair_rows: list[dict[str, object]] = []
        channel_labels = [int(idx) for idx in channel_map]
        for local_i in range(active_mix.shape[1]):
            for local_j in range(local_i + 1, active_mix.shape[1]):
                corr, lags = _gcc_phat(
                    strongest_window[:, local_i],
                    strongest_window[:, local_j],
                    sample_rate_hz=int(speaker_recording.sample_rate_hz),
                    max_tau_s=float(np.linalg.norm(mic_geometry_xyz[local_i] - mic_geometry_xyz[local_j]) / 343.0),
                    bandlimit_hz=3500.0,
                )
                if corr.size == 0:
                    continue
                peak_idx = int(np.argmax(corr))
                pair_rows.append(
                    {
                        "pair_label": f"ch{channel_labels[local_i]}-ch{channel_labels[local_j]}",
                        "lag_samples": lags.astype(np.int64).tolist(),
                        "corr": np.asarray(corr, dtype=np.float64).tolist(),
                        "peak_lag_samples": int(lags[peak_idx]),
                        "peak_value": float(corr[peak_idx]),
                    }
                )
        _write_gcc_phat_pair_plot(
            output_dir / "gcc_phat_pair_peaks_strongest_window.png",
            pair_rows=pair_rows,
            sample_rate_hz=int(speaker_recording.sample_rate_hz),
            window_start_sec=float(strongest_start / float(speaker_recording.sample_rate_hz)),
        )
        (output_dir / "gcc_phat_pair_peaks_strongest_window.json").write_text(
            json.dumps(
                {
                    "window_start_sample": int(strongest_start),
                    "window_start_sec": float(strongest_start / float(speaker_recording.sample_rate_hz)),
                    "window_rms": float(window_rms[strongest_idx]),
                    "pairs": pair_rows,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    predictions_path = output_dir / "predictions.json"
    predictions_path.write_text(json.dumps(predictions, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "identifier": str(identifier),
        "speaker_recording_id": str(speaker_recording.recording_id),
        "noise_recording_id": str(noise_recording.recording_id),
        "sample_rate_hz": int(speaker_recording.sample_rate_hz),
        "window_ms": int(_WINDOW_MS),
        "frame_count": int(len(predictions)),
        "predicted_frame_count": int(len(valid_predictions)),
        "ground_truth_doa_deg": float(target_doa_deg),
        "mean_absolute_error_deg": None if errors.size == 0 else float(np.mean(errors)),
        "median_absolute_error_deg": None if errors.size == 0 else float(np.median(errors)),
        "max_absolute_error_deg": None if errors.size == 0 else float(np.max(errors)),
        "noise_mode": str(args.noise_mode),
        "noise_scale": float(args.noise_scale),
        "method": str(args.method),
        "spectrum_ema_alpha": float(args.spectrum_ema_alpha),
        "average_spectrum_frame_count": int(spectrum_count),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), **summary}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
