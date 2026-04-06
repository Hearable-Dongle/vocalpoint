from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from validate.common import (
        AMPLIFICATION_OUTPUT_ROOT,
        SUPPRESSION_OUTPUT_ROOT,
        active_channel_map_for_recording,
        aggregate_results_by_distance,
        align_recordings,
        discover_recording_dirs,
        evaluate_mode,
        generate_white_noise_like,
        identifier_for_recording,
        load_recording,
        mix_speaker_and_noise,
        recording_direction_deg,
        recording_distance_m,
        reference_mono_from_speaker,
        save_mode_outputs,
    )
else:  # pragma: no cover
    from validate.common import (
        AMPLIFICATION_OUTPUT_ROOT,
        SUPPRESSION_OUTPUT_ROOT,
        active_channel_map_for_recording,
        aggregate_results_by_distance,
        align_recordings,
        discover_recording_dirs,
        evaluate_mode,
        generate_white_noise_like,
        identifier_for_recording,
        load_recording,
        mix_speaker_and_noise,
        recording_direction_deg,
        recording_distance_m,
        reference_mono_from_speaker,
        save_mode_outputs,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk-validate amplification and own-voice-suppression across many speaker captures and one noise capture.")
    parser.add_argument("--speaker-dir", required=True, help="Directory containing one or more collected speaker recording directories.")
    parser.add_argument("--noise-dir", help="Path to one collected noise recording directory.")
    parser.add_argument(
        "--noise-mode",
        choices=("recorded", "white"),
        default="recorded",
        help="Noise source to mix with each speaker recording. Default: recorded.",
    )
    parser.add_argument(
        "--processing-mode",
        choices=("callback", "entrypoint", "local", "passthrough", "research_adapter"),
        default="callback",
        help="Validation processing path. Default: callback.",
    )
    parser.add_argument(
        "--noise-scale",
        type=float,
        default=1.0,
        help="Multiplier applied to RMS-matched noise before averaging with the speaker signal. Default: 1.0.",
    )
    parser.add_argument(
        "--output-rms-match-input",
        action="store_true",
        help="Scale processed mono output so its RMS matches the raw input mono before metrics/output save.",
    )
    parser.add_argument("--white-noise-seed", type=int, default=0, help="Base random seed for white-noise generation.")
    args = parser.parse_args()

    noise_recording = None if args.noise_mode == "white" else load_recording(args.noise_dir) if args.noise_dir else None
    if args.noise_mode == "recorded" and noise_recording is None:
        raise ValueError("--noise-dir is required when --noise-mode=recorded")
    speaker_dirs = discover_recording_dirs(args.speaker_dir)
    if not speaker_dirs:
        raise FileNotFoundError(f"no speaker recordings found under {args.speaker_dir}")

    amplification_rows: list[dict[str, object]] = []
    suppression_rows: list[dict[str, object]] = []

    for speaker_dir in speaker_dirs:
        speaker_recording = load_recording(speaker_dir)
        if args.noise_mode == "recorded":
            assert noise_recording is not None
            speaker_mc, noise_mc = align_recordings(speaker_recording, noise_recording)
            noise_recording_for_outputs = noise_recording
        else:
            speaker_mc = align_recordings(speaker_recording, speaker_recording)[0]
            noise_mc = generate_white_noise_like(speaker_mc, seed=int(args.white_noise_seed) + len(amplification_rows))
            noise_recording_for_outputs = speaker_recording
        channel_map = active_channel_map_for_recording(speaker_recording)
        mix_mc = mix_speaker_and_noise(
            speaker_mc,
            noise_mc,
            channel_map=channel_map,
            noise_scale=float(args.noise_scale),
        )
        clean_ref_mono = reference_mono_from_speaker(
            speaker_mc,
            channel_map=channel_map,
        )
        identifier = identifier_for_recording(speaker_recording)

        amplification = evaluate_mode(
            mix_mc=mix_mc,
            clean_ref_mono=clean_ref_mono,
            speaker_recording=speaker_recording,
            mode="amplification",
            suppression_enabled=False,
            suppression_doa_deg=None,
            processing_mode=str(args.processing_mode),
            output_rms_match_input=bool(args.output_rms_match_input),
        )
        suppression = evaluate_mode(
            mix_mc=mix_mc,
            clean_ref_mono=clean_ref_mono,
            speaker_recording=speaker_recording,
            mode="own_voice_suppression",
            suppression_enabled=True,
            suppression_doa_deg=recording_direction_deg(speaker_recording),
            processing_mode=str(args.processing_mode),
            output_rms_match_input=bool(args.output_rms_match_input),
        )

        save_mode_outputs(
            output_root=AMPLIFICATION_OUTPUT_ROOT,
            identifier=identifier,
            mix_mc=mix_mc,
            clean_ref_mono=clean_ref_mono,
            noise_mc=noise_mc,
            result=amplification,
            speaker_recording=speaker_recording,
            noise_recording=noise_recording_for_outputs,
        )
        save_mode_outputs(
            output_root=SUPPRESSION_OUTPUT_ROOT,
            identifier=identifier,
            mix_mc=mix_mc,
            clean_ref_mono=clean_ref_mono,
            noise_mc=noise_mc,
            result=suppression,
            speaker_recording=speaker_recording,
            noise_recording=noise_recording_for_outputs,
        )

        amplification_rows.append(
            {
                "identifier": identifier,
                "distance_m": recording_distance_m(speaker_recording),
                **dict(amplification["metrics"]),
            }
        )
        suppression_rows.append(
            {
                "identifier": identifier,
                "distance_m": recording_distance_m(speaker_recording),
                **dict(suppression["metrics"]),
            }
        )

    amplification_summary = aggregate_results_by_distance(amplification_rows)
    suppression_summary = aggregate_results_by_distance(suppression_rows)

    AMPLIFICATION_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    SUPPRESSION_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (AMPLIFICATION_OUTPUT_ROOT / "bulk_summary_by_distance.json").write_text(
        json.dumps({"rows": amplification_rows, "summary_by_distance": amplification_summary}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (SUPPRESSION_OUTPUT_ROOT / "bulk_summary_by_distance.json").write_text(
        json.dumps({"rows": suppression_rows, "summary_by_distance": suppression_summary}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "speaker_count": len(speaker_dirs),
                "noise_mode": str(args.noise_mode),
                "noise_scale": float(args.noise_scale),
                "processing_mode": str(args.processing_mode),
                "output_rms_match_input": bool(args.output_rms_match_input),
                "amplification_summary_by_distance": amplification_summary,
                "own_voice_suppression_summary_by_distance": suppression_summary,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
