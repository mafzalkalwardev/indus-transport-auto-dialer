"""Generate tiny synthetic WAV samples for offline detector checks.

These samples are intentionally simple and dependency-free. They exercise the
energy, cadence, and transcript paths without shipping large models or real
call recordings.
"""
from __future__ import annotations

import argparse
import math
import os
import wave


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "tests", "audio")
SAMPLE_RATE = 16000


def _write_wav(path: str, samples: list[float], sample_rate: int = SAMPLE_RATE) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        data = bytearray()
        for sample in samples:
            value = int(max(-1.0, min(1.0, sample)) * 32767)
            data.extend(value.to_bytes(2, byteorder="little", signed=True))
        wf.writeframes(bytes(data))


def _tone(freq: float, seconds: float, amp: float = 0.25) -> list[float]:
    return [
        amp * math.sin(2.0 * math.pi * freq * i / SAMPLE_RATE)
        for i in range(int(seconds * SAMPLE_RATE))
    ]


def _silence(seconds: float) -> list[float]:
    return [0.0] * int(seconds * SAMPLE_RATE)


def _noise(seconds: float, amp: float = 0.04) -> list[float]:
    # Deterministic pseudo-noise so generated files are reproducible.
    x = 17
    out: list[float] = []
    for _ in range(int(seconds * SAMPLE_RATE)):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        out.append((((x / 0x7FFFFFFF) * 2.0) - 1.0) * amp)
    return out


def _speech_like(seconds: float) -> list[float]:
    samples: list[float] = []
    total = int(seconds * SAMPLE_RATE)
    for i in range(total):
        env = 0.5 + 0.5 * math.sin(2.0 * math.pi * 4.0 * i / SAMPLE_RATE)
        sample = (
            0.16 * math.sin(2.0 * math.pi * 180.0 * i / SAMPLE_RATE)
            + 0.06 * math.sin(2.0 * math.pi * 310.0 * i / SAMPLE_RATE)
        )
        samples.append(sample * env)
    return samples


def generate(output_dir: str) -> list[str]:
    files = {
        os.path.join(output_dir, "human", "hello_like.wav"): _speech_like(0.9),
        os.path.join(output_dir, "voicemail", "message_beep.wav"): (
            _speech_like(4.5) + _silence(0.2) + _tone(1000.0, 0.35, 0.35)
        ),
        os.path.join(output_dir, "ringback", "ringback_like.wav"): (
            _tone(440.0, 1.0) + _silence(2.0) + _tone(440.0, 1.0) + _silence(2.0)
        ),
        os.path.join(output_dir, "silence", "silence.wav"): _silence(1.0),
        os.path.join(output_dir, "noise", "low_noise.wav"): _noise(1.0),
    }
    written: list[str] = []
    for path, samples in files.items():
        _write_wav(path, samples)
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate small synthetic detector WAV samples.")
    parser.add_argument("--output-dir", default=DEFAULT_OUT)
    args = parser.parse_args()
    for path in generate(args.output_dir):
        print(path)


if __name__ == "__main__":
    main()
