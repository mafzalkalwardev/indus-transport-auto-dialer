"""List/test local audio devices for AI call detection."""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.audio_analyzer import AudioAnalyzer


def main() -> None:
    parser = argparse.ArgumentParser(description="Test local call audio capture.")
    parser.add_argument("--device", default="", help="Device index/name, blank for default output loopback")
    parser.add_argument("--seconds", type=float, default=2.0)
    args = parser.parse_args()

    devices = AudioAnalyzer.list_audio_devices()
    if not devices:
        print("AI Audio: NO BACKEND")
        print("Install sounddevice and ensure Windows audio devices are available.")
    else:
        print("Audio devices:")
        for dev in devices:
            print(
                f"  {dev['index']}: {dev['name']} "
                f"in={dev['max_input_channels']} out={dev['max_output_channels']}"
            )

    analyzer = AudioAnalyzer(
        enable_audio=True,
        device=args.device or None,
        chunk_seconds=max(0.2, float(args.seconds)),
    )
    features = analyzer.get_features_real_time()
    recommended = AudioAnalyzer.recommend_capture_device()
    print("\nCapture result:")
    print(f"AI Audio: {features.backend_status}")
    if recommended and not args.device:
        print(f"recommended_device={recommended}  (set audio_device in dialer_config.json)")
    print(f"backend={features.backend_name}")
    print(f"rms={features.rms:.4f}")
    print(f"speech_like={features.has_speech_like}")
    print(f"ringback={features.ringback_cadence_confidence:.2f}")
    print(f"busy={features.busy_tone_cadence_confidence:.2f}")
    print(f"beep={features.beep_detected}")
    print(f"vad_backend={features.vad_backend}")
    print(f"vad_confidence={features.vad_confidence:.2f}")
    print(f"reason={features.reason}")


if __name__ == "__main__":
    main()
