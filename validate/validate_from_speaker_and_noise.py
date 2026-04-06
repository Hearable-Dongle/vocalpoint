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
        align_recordings,
        evaluate_mode,
        generate_white_noise_like,
        identifier_for_recording,
        load_recording,
        mix_speaker_and_noise,
        recording_direction_deg,
        reference_mono_from_speaker,
        save_mode_outputs,
    )
else:  # pragma: no cover
    from validate.common import (
        AMPLIFICATION_OUTPUT_ROOT,
        SUPPRESSION_OUTPUT_ROOT,
        active_channel_map_for_recording,
        align_recordings,
        evaluate_mode,
        generate_white_noise_like,
        identifier_for_recording,
        load_recording,
        mix_speaker_and_noise,
        recording_direction_deg,
        reference_mono_from_speaker,
        save_mode_outputs,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate amplification and own-voice-suppression from one speaker capture and one noise capture.")
    parser.add_argument("--speaker-dir", required=True, help="Path to one collected speaker recording directory.")
    parser.add_argument("--noise-dir", help="Path to one collected noise recording directory.")
    parser.add_argument(
        "--noise-mode",
        choices=("recorded", "white"),
        default="recorded",
        help="Noise source to mix with the speaker recording. Default: recorded.",
    )
    parser.add_argument(
        "--processing-mode",
        choices=("callback", "local", "passthrough"),
        default="callback",
        help="Validation processing path. Default: callback.",
    )
    parser.add_argument("--white-noise-seed", type=int, default=0, help="Random seed for white-noise generation.")
    args = parser.parse_args()

    speaker_recording = load_recording(args.speaker_dir)
    if args.noise_mode == "recorded":
        if not args.noise_dir:
            raise ValueError("--noise-dir is required when --noise-mode=recorded")
        noise_recording = load_recording(args.noise_dir)
        speaker_mc, noise_mc = align_recordings(speaker_recording, noise_recording)
    else:
        speaker_mc = align_recordings(speaker_recording, speaker_recording)[0]
        noise_mc = generate_white_noise_like(speaker_mc, seed=int(args.white_noise_seed))
        noise_recording = speaker_recording
    channel_map = active_channel_map_for_recording(speaker_recording)
    mix_mc = mix_speaker_and_noise(speaker_mc, noise_mc, channel_map=channel_map)
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
    )
    suppression = evaluate_mode(
        mix_mc=mix_mc,
        clean_ref_mono=clean_ref_mono,
        speaker_recording=speaker_recording,
        mode="own_voice_suppression",
        suppression_enabled=True,
        suppression_doa_deg=recording_direction_deg(speaker_recording),
        processing_mode=str(args.processing_mode),
    )

    amp_dir = save_mode_outputs(
        output_root=AMPLIFICATION_OUTPUT_ROOT,
        identifier=identifier,
        mix_mc=mix_mc,
        clean_ref_mono=clean_ref_mono,
        noise_mc=noise_mc,
        result=amplification,
        speaker_recording=speaker_recording,
        noise_recording=noise_recording,
    )
    suppression_dir = save_mode_outputs(
        output_root=SUPPRESSION_OUTPUT_ROOT,
        identifier=identifier,
        mix_mc=mix_mc,
        clean_ref_mono=clean_ref_mono,
        noise_mc=noise_mc,
        result=suppression,
        speaker_recording=speaker_recording,
        noise_recording=noise_recording,
    )

    print(
        json.dumps(
            {
                "identifier": identifier,
                "amplification_output_dir": str(amp_dir),
                "own_voice_suppression_output_dir": str(suppression_dir),
                "noise_mode": str(args.noise_mode),
                "processing_mode": str(args.processing_mode),
                "amplification_metrics": amplification["metrics"],
                "own_voice_suppression_metrics": suppression["metrics"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
