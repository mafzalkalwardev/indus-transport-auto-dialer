"""Run the local hybrid detector against WAV files and print evidence."""
from __future__ import annotations

import argparse
import os
import sys
import wave


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.audio_analyzer import AudioAnalyzer
from src.local_call_detector import DetectionConfig, LocalCallDetector


def _read_wav(path: str) -> tuple[list[float], int]:
    with wave.open(path, "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    if width != 2:
        raise ValueError(f"{path}: expected 16-bit PCM WAV")
    values: list[float] = []
    step = channels * width
    for offset in range(0, len(frames), step):
        channel_values = []
        for channel in range(channels):
            start = offset + channel * width
            raw = int.from_bytes(frames[start:start + width], byteorder="little", signed=True)
            channel_values.append(raw / 32768.0)
        values.append(sum(channel_values) / max(1, len(channel_values)))
    return values, sample_rate


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline WAV files through the local detector.")
    parser.add_argument("wav", nargs="+", help="WAV file(s) to analyze")
    parser.add_argument("--transcript", default="", help="Optional transcript text to feed phrase detectors")
    parser.add_argument("--dom-state", default="CONNECTED_CTRL")
    parser.add_argument("--elapsed-seconds", type=float, default=10.0)
    args = parser.parse_args()

    analyzer = AudioAnalyzer(enable_audio=True)
    detector = LocalCallDetector(DetectionConfig(decision_stability_window=1))
    for path in args.wav:
        samples, sample_rate = _read_wav(path)
        features = analyzer.analyze_from_pcm(samples, sample_rate=sample_rate, transcript=args.transcript)
        result = detector.detect(
            features,
            {
                "state": args.dom_state,
                "hasEnabledAnswerControl": args.dom_state.upper() == "CONNECTED_CTRL",
                "hasTimer": args.dom_state.upper() == "CONNECTED",
                "callText": args.transcript,
            },
            {"elapsed_seconds": args.elapsed_seconds, "state": "RINGING"},
        )
        print(
            f"{path}: state={result.state.value} confidence={result.confidence:.3f} "
            f"priority={result.priority} reason={result.reason}"
        )
        print(
            "  evidence="
            f"audio_state={result.evidence.get('audio_state')} "
            f"speech={getattr(features, 'speech_duration_seconds', 0.0):.2f}s "
            f"vad={getattr(features, 'vad_confidence', 0.0):.2f} "
            f"ringback={getattr(features, 'ringback_cadence_confidence', 0.0):.2f} "
            f"beep={getattr(features, 'beep_detected', False)}"
        )


if __name__ == "__main__":
    main()
