#!/usr/bin/env python3
"""Quick harness for AMD + pacing modules (skips live audio when unavailable)."""
from __future__ import annotations

import math
import sys


def test_tone_detector() -> None:
    from src.detection.tone_detector import detect_tones

    samples = [math.sin(2 * math.pi * 440 * i / 16000) for i in range(8000)]
    result = detect_tones(samples, sample_rate=16000)
    assert result.beep_detected, "440Hz beep should be detected"


def test_pacing_math() -> None:
    from src.pacing.engine import PredictivePacingEngine, PacingMetrics

    engine = PredictivePacingEngine()
    dials = engine.calculate_dials_needed(
        PacingMetrics(agents_available=2, connect_rate=0.2, abandon_rate=0.0, calls_in_progress=0)
    )
    assert dials >= 1


def test_websocket_optional() -> None:
    try:
        import websockets  # noqa: F401
    except ImportError:
        print("websockets not installed — skipping")
        return
    from src.ui.websocket_manager import WebSocketServerThread

    assert WebSocketServerThread is not None


def main() -> int:
    tests = [test_tone_detector, test_pacing_math, test_websocket_optional]
    for fn in tests:
        name = fn.__name__
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:
            print(f"FAIL {name}: {exc}")
            return 1
    print("All run_full_test checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
