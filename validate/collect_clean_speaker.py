from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from validation.common import (
        DEFAULT_DOA_DEG,
        DEFAULT_DURATION_SEC,
        DEFAULT_MIC_PROFILE,
        default_speaker_output_path,
        now_iso,
        record_multichannel_audio,
        resolve_capture_output_dir,
        save_raw_channels,
        speaker_capture_metadata,
        write_metadata,
    )
else:  # pragma: no cover
    from validation.common import (
        DEFAULT_DOA_DEG,
        DEFAULT_DURATION_SEC,
        DEFAULT_MIC_PROFILE,
        default_speaker_output_path,
        now_iso,
        record_multichannel_audio,
        resolve_capture_output_dir,
        save_raw_channels,
        speaker_capture_metadata,
        write_metadata,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect a clean multichannel speaker recording using the ReSpeaker3000 profile.")
    parser.add_argument(
        "--output-path",
        default=None,
        help="Output path relative to signal-processing-research/validation/outputs/speakers/. Default: auto-generated from speaker id, distance, and DOA.",
    )
    parser.add_argument("--speaker-id", required=True, help="Speaker identifier.")
    parser.add_argument("--distance-m", type=float, required=True, help="Distance from microphone in metres.")
    parser.add_argument("--duration-sec", type=float, default=DEFAULT_DURATION_SEC, help="Capture duration in seconds. Default: 8.")
    parser.add_argument("--doa-deg", type=float, default=DEFAULT_DOA_DEG, help="Speaker DOA in degrees. Default: 0.")
    parser.add_argument("--device-query", default=None, help="Optional substring used to select the input audio device.")
    args = parser.parse_args()

    relative_output_path = str(
        args.output_path
        or default_speaker_output_path(
            speaker_id=str(args.speaker_id),
            distance_m=float(args.distance_m),
            doa_deg=float(args.doa_deg),
            mic_profile=DEFAULT_MIC_PROFILE,
        )
    )
    output_dir = resolve_capture_output_dir(kind="speaker", relative_output_path=relative_output_path)
    started_at_iso = now_iso()
    audio_mc, device_name = record_multichannel_audio(
        duration_sec=float(args.duration_sec),
        sample_rate_hz=int(DEFAULT_MIC_PROFILE.sample_rate_hz),
        channel_count=int(DEFAULT_MIC_PROFILE.channel_count),
        device_query=None if args.device_query is None else str(args.device_query),
        allow_keyboard_stop=True,
    )
    stopped_at_iso = now_iso()
    channels = save_raw_channels(audio_mc, sample_rate_hz=int(DEFAULT_MIC_PROFILE.sample_rate_hz), output_dir=output_dir)
    metadata = speaker_capture_metadata(
        recording_id=str(Path(relative_output_path).name or "speaker-recording"),
        device_name=str(device_name),
        mic_profile=DEFAULT_MIC_PROFILE,
        sample_rate_hz=int(DEFAULT_MIC_PROFILE.sample_rate_hz),
        started_at_iso=started_at_iso,
        stopped_at_iso=stopped_at_iso,
        channels=channels,
        speaker_id=str(args.speaker_id),
        distance_m=float(args.distance_m),
        doa_deg=float(args.doa_deg),
        duration_sec=float(audio_mc.shape[0]) / float(DEFAULT_MIC_PROFILE.sample_rate_hz),
    )
    write_metadata(output_dir, metadata)
    print(f"Saved clean speaker capture to {output_dir}")


if __name__ == "__main__":
    main()
