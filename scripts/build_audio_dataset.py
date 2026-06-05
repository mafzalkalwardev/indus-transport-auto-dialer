"""
Build the labelled training dataset for the AI call-progress classifier.

Two sources, combined:

1. **Synthesised telephony call-progress tones** — ringback, busy, reorder/SIT,
   dial tone and the voicemail "beep".  These are generated at the exact
   published telephony frequencies/cadences, so they are perfectly labelled.

2. **Real human-voice samples downloaded from the internet** — public-domain
   spoken-sentence recordings from the Open Speech Repository (8 kHz, the
   telephony band).  These provide the HUMAN (live pickup) and VOICEMAIL
   (machine greeting) speech material.

Output: ``data/audio_dataset/dataset.npz`` with feature matrix ``X``, integer
labels ``y`` and the label list.  Downloaded clips are cached under
``data/audio_dataset/voice_cache/`` so re-runs are offline/fast.

Run:  python scripts/build_audio_dataset.py
"""
from __future__ import annotations

import os
import ssl
import sys
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.call_audio_ai import (  # noqa: E402
    LABELS, SAMPLE_RATE, WINDOW_SEC, extract_features,
)

SR = SAMPLE_RATE
WIN = int(WINDOW_SEC * SR)
RNG = np.random.default_rng(1234)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "audio_dataset",
)
VOICE_CACHE = os.path.join(DATA_DIR, "voice_cache")

# Public-domain spoken-sentence recordings (Open Speech Repository, 8 kHz).
VOICE_URLS = [
    "https://www.voiptroubleshooter.com/open_speech/american/OSR_us_000_0010_8k.wav",
    "https://www.voiptroubleshooter.com/open_speech/american/OSR_us_000_0011_8k.wav",
    "https://www.voiptroubleshooter.com/open_speech/american/OSR_us_000_0012_8k.wav",
    "https://www.voiptroubleshooter.com/open_speech/american/OSR_us_000_0013_8k.wav",
    "https://www.voiptroubleshooter.com/open_speech/american/OSR_us_000_0014_8k.wav",
    "https://www.voiptroubleshooter.com/open_speech/british/OSR_uk_000_0020_8k.wav",
    "https://www.voiptroubleshooter.com/open_speech/british/OSR_uk_000_0021_8k.wav",
]

_HDRS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.voiptroubleshooter.com/open_speech/",
}


# ── Tone synthesis ────────────────────────────────────────────────────────────
def _tone(freqs, dur, sr=SR, amp=0.3):
    t = np.arange(int(dur * sr)) / sr
    sig = np.zeros_like(t)
    for f in freqs:
        sig += np.sin(2 * np.pi * f * t)
    return amp * sig / max(1, len(freqs))


def _silence(dur, sr=SR):
    return np.zeros(int(dur * sr))


def _line_noise(n, level=0.004):
    # Faint 60 Hz hum + white noise → realistic phone-line bed.
    t = np.arange(n) / SR
    return level * (RNG.standard_normal(n) + 0.5 * np.sin(2 * np.pi * 60 * t))


def _fit_window(sig):
    if len(sig) < WIN:
        sig = np.pad(sig, (0, WIN - len(sig)))
    return sig[:WIN]


def _augment(sig):
    sig = sig + _line_noise(len(sig), level=RNG.uniform(0.001, 0.02))
    sig = sig * RNG.uniform(0.5, 1.2)                      # gain variation
    peak = np.max(np.abs(sig)) + 1e-9
    if peak > 0.99:
        sig = 0.99 * sig / peak
    return sig


def make_ringback():
    style = RNG.integers(0, 2)
    if style == 0:           # North American 440+480 Hz, continuous within window
        sig = _tone([440, 480], WINDOW_SEC, amp=RNG.uniform(0.2, 0.4))
    else:                    # European single 425 Hz, 1s on / 4s off → mostly on
        sig = _tone([425], WINDOW_SEC, amp=RNG.uniform(0.2, 0.4))
    return _fit_window(_augment(sig))


def make_busy():
    if RNG.integers(0, 2) == 0:   # busy 480+620, 0.5 on / 0.5 off
        on = _tone([480, 620], 0.5, amp=RNG.uniform(0.2, 0.4))
        seg = np.concatenate([on, _silence(0.5)])
    else:                         # reorder/SIT 913.8/1370.6/1776.7 short tones
        a = _tone([913.8], 0.276, amp=0.3)
        b = _tone([1370.6], 0.276, amp=0.3)
        c = _tone([1776.7], 0.380, amp=0.3)
        seg = np.concatenate([a, b, c, _silence(0.2)])
    return _fit_window(_augment(np.tile(seg, 3)))


def make_beep():
    # Voicemail record beep: 1000 Hz (sometimes 1400) ~0.3-0.5s + silence.
    f = RNG.choice([1000.0, 1400.0])
    pre = _silence(RNG.uniform(0.1, 0.3))
    beep = _tone([f], RNG.uniform(0.3, 0.5), amp=RNG.uniform(0.25, 0.45))
    return _fit_window(_augment(np.concatenate([pre, beep, _silence(0.4)])))


def make_silence():
    return _fit_window(_line_noise(WIN, level=RNG.uniform(0.0005, 0.006)))


# ── Voice-based windows (HUMAN vs VOICEMAIL) ──────────────────────────────────
def _download_voice():
    os.makedirs(VOICE_CACHE, exist_ok=True)
    import soundfile as sf
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    clips = []
    for url in VOICE_URLS:
        name = url.rsplit("/", 1)[-1]
        path = os.path.join(VOICE_CACHE, name)
        if not os.path.exists(path):
            try:
                req = urllib.request.Request(url, headers=_HDRS)
                with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                    open(path, "wb").write(r.read())
                print(f"  downloaded {name}")
            except Exception as e:  # noqa: BLE001
                print(f"  WARN could not download {name}: {e}")
                continue
        try:
            audio, sr = sf.read(path)
            if audio.ndim == 2:
                audio = audio.mean(axis=1)
            if sr != SR:               # cheap linear resample to 8 kHz
                idx = np.linspace(0, len(audio) - 1, int(len(audio) * SR / sr))
                audio = np.interp(idx, np.arange(len(audio)), audio)
            audio = audio / (np.max(np.abs(audio)) + 1e-9)
            clips.append(audio.astype(np.float64))
        except Exception as e:  # noqa: BLE001
            print(f"  WARN could not read {name}: {e}")
    return clips


def _synth_speech_fallback(n_clips=4, dur=12.0):
    """Formant-ish voiced/unvoiced surrogate when downloads are unavailable."""
    clips = []
    for _ in range(n_clips):
        n = int(dur * SR)
        t = np.arange(n) / SR
        sig = np.zeros(n)
        pos = 0
        while pos < n:
            seg = int(RNG.uniform(0.15, 0.5) * SR)
            voiced = RNG.random() < 0.65
            s = slice(pos, min(n, pos + seg))
            tt = t[s]
            if voiced:
                f0 = RNG.uniform(90, 220)
                for k, a in enumerate([1.0, 0.5, 0.3, 0.2], start=1):
                    sig[s] += a * np.sin(2 * np.pi * f0 * k * tt)
                for fmt in (RNG.uniform(500, 900), RNG.uniform(1200, 2400)):
                    sig[s] += 0.3 * np.sin(2 * np.pi * fmt * tt)
            else:
                sig[s] += 0.6 * RNG.standard_normal(len(tt))
            pos += seg + int(RNG.uniform(0.0, 0.12) * SR)
        sig /= (np.max(np.abs(sig)) + 1e-9)
        clips.append(sig)
    return clips


def make_human(clip):
    """Live pickup: a short utterance ("hello?") then the caller waits → pause."""
    speak = RNG.uniform(0.3, 1.1)
    start = RNG.integers(0, max(1, len(clip) - int(speak * SR)))
    burst = clip[start:start + int(speak * SR)] * RNG.uniform(0.4, 0.9)
    lead = _silence(RNG.uniform(0.0, 0.25))
    sig = np.concatenate([lead, burst, _silence(WINDOW_SEC)])
    return _fit_window(_augment(sig))


def make_voicemail_speech(clip):
    """Machine greeting: continuous speech filling the whole window."""
    if len(clip) <= WIN:
        seg = np.tile(clip, 2)
    else:
        start = RNG.integers(0, len(clip) - WIN)
        seg = clip[start:start + WIN]
    seg = seg * RNG.uniform(0.4, 0.9)
    return _fit_window(_augment(seg))


# ── Build ─────────────────────────────────────────────────────────────────────
def build(per_class=500):
    os.makedirs(DATA_DIR, exist_ok=True)
    print("Fetching public-domain voice samples…")
    clips = _download_voice()
    if len(clips) < 2:
        print("  using synthetic speech fallback (downloads unavailable)")
        clips = _synth_speech_fallback()

    X, y = [], []
    label_idx = {lab: i for i, lab in enumerate(LABELS)}

    def add(label, sig):
        X.append(extract_features(sig, SR))
        y.append(label_idx[label])

    print(f"Generating {per_class} windows per class…")
    for _ in range(per_class):
        add("RINGBACK", make_ringback())
        add("BUSY", make_busy())
        add("SILENCE", make_silence())
        # Voicemail: mix of beeps and continuous greeting speech.
        if RNG.random() < 0.4:
            add("VOICEMAIL", make_beep())
        else:
            add("VOICEMAIL", make_voicemail_speech(clips[RNG.integers(len(clips))]))
        add("HUMAN", make_human(clips[RNG.integers(len(clips))]))

    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.int64)
    out = os.path.join(DATA_DIR, "dataset.npz")
    np.savez_compressed(out, X=X, y=y, labels=np.array(LABELS))
    print(f"Saved {X.shape[0]} samples × {X.shape[1]} features → {out}")
    return out


if __name__ == "__main__":
    build()
