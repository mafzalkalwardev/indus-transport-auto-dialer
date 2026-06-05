"""
AI Call-Progress-Analysis (CPA / Answering-Machine-Detection) module.

Classifies short windows of *call audio* into one of:

    RINGBACK   – outbound ring tone (line is ringing, nobody has picked up)
    HUMAN      – a live person answered ("hello?") → CONNECTED / picked up
    VOICEMAIL  – answering-machine / voicemail greeting or beep
    SILENCE    – dead air (call not progressing yet, or muted)
    BUSY       – busy signal / SIT reorder tone (number unavailable)

This is the industry-standard way carriers, Asterisk and Twilio decide
"answer vs. machine".  The feature extractor below is **pure numpy** so it
is fast on CPU and adds no heavy deep-learning dependency, which keeps the
packaged Windows EXE small.

The trained scikit-learn model lives at ``models/call_progress_model.joblib``
(built by ``scripts/train_call_model.py``).  If the model file is missing the
classifier transparently falls back to a deterministic rule-based detector so
the app never crashes when the model has not been shipped.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Optional

import numpy as np

# ── Audio constants ───────────────────────────────────────────────────────────
SAMPLE_RATE = 8000          # telephony band — call-progress energy lives < 3.4 kHz
WINDOW_SEC = 1.0            # analysis window fed to the classifier
FRAME_LEN = 256             # ~32 ms STFT frame at 8 kHz
FRAME_HOP = 128             # 50 % overlap
N_MELS = 26
N_MFCC = 13

# ── Labels ──────────────────────────────────────────────────────────────────
LABELS = ["RINGBACK", "HUMAN", "VOICEMAIL", "SILENCE", "BUSY"]

# Map an audio label → the call state used by the rest of the app.
LABEL_TO_STATE = {
    "RINGBACK": "RINGING",
    "HUMAN": "CONNECTED",
    "VOICEMAIL": "VOICEMAIL",
    "SILENCE": "RINGING",   # not progressed yet — keep ringing, never a false answer
    "BUSY": "FAILED",
}

# Telephony call-progress reference frequencies (Hz) used as targeted features.
_TONE_FREQS = [350.0, 440.0, 480.0, 620.0, 950.0, 1000.0, 1400.0, 1800.0]

# Default location of the trained model artifact.
DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "call_progress_model.joblib",
)


# ── Low-level DSP helpers (pure numpy) ────────────────────────────────────────
def _to_mono_float(samples: np.ndarray) -> np.ndarray:
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim == 2:                       # stereo → mono
        x = x.mean(axis=1)
    if x.size == 0:
        return x
    peak = float(np.max(np.abs(x)))
    if peak > 1.0:                        # int16/float scaled to ±32768 → normalise
        x = x / peak
    return x


def _frame_signal(x: np.ndarray, frame_len: int, hop: int) -> np.ndarray:
    if x.size < frame_len:
        x = np.pad(x, (0, frame_len - x.size))
    n_frames = 1 + (x.size - frame_len) // hop
    if n_frames < 1:
        n_frames = 1
    idx = np.arange(frame_len)[None, :] + hop * np.arange(n_frames)[:, None]
    idx = np.clip(idx, 0, x.size - 1)
    frames = x[idx] * np.hanning(frame_len)[None, :]
    return frames


def _power_spectrum(frames: np.ndarray, n_fft: int) -> np.ndarray:
    spec = np.fft.rfft(frames, n=n_fft, axis=1)
    return (np.abs(spec) ** 2) / n_fft


def _hz_to_mel(hz: np.ndarray) -> np.ndarray:
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def _mel_filterbank(n_mels: int, n_fft: int, sr: int) -> np.ndarray:
    low_mel = _hz_to_mel(np.array([0.0]))[0]
    high_mel = _hz_to_mel(np.array([sr / 2.0]))[0]
    mel_pts = np.linspace(low_mel, high_mel, n_mels + 2)
    hz_pts = _mel_to_hz(mel_pts)
    bins = np.floor((n_fft + 1) * hz_pts / sr).astype(int)
    bins = np.clip(bins, 0, n_fft // 2)
    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for m in range(1, n_mels + 1):
        left, center, right = bins[m - 1], bins[m], bins[m + 1]
        if center == left:
            center = left + 1
        if right == center:
            right = center + 1
        for k in range(left, center):
            if center != left:
                fb[m - 1, k] = (k - left) / (center - left)
        for k in range(center, right):
            if right != center:
                fb[m - 1, k] = (right - k) / (right - center)
    return fb


_MEL_FB_CACHE: dict[tuple[int, int, int], np.ndarray] = {}


def _get_mel_fb(n_mels: int, n_fft: int, sr: int) -> np.ndarray:
    key = (n_mels, n_fft, sr)
    if key not in _MEL_FB_CACHE:
        _MEL_FB_CACHE[key] = _mel_filterbank(n_mels, n_fft, sr)
    return _MEL_FB_CACHE[key]


def _dct(x: np.ndarray, n_out: int) -> np.ndarray:
    n = x.shape[-1]
    k = np.arange(n_out)[:, None]
    m = np.arange(n)[None, :]
    basis = np.cos(math.pi / n * (m + 0.5) * k)
    return basis @ x.T  # (n_out, frames)


# ── Feature names (kept in sync with extract_features) ────────────────────────
FEATURE_NAMES: list[str] = (
    [
        "rms_mean", "rms_std", "rms_max",
        "zcr_mean", "zcr_std",
        "centroid_mean", "centroid_std",
        "rolloff_mean",
        "flatness_mean", "flatness_std",
        "dom_freq_mean", "dom_freq_std",
        "peak_ratio_mean", "peak_ratio_max",
        "low_band_ratio", "voice_band_ratio",
        "energy_var_ratio",
    ]
    + [f"tone_{int(f)}" for f in _TONE_FREQS]
    + [f"mfcc{i}_mean" for i in range(N_MFCC)]
    + [f"mfcc{i}_std" for i in range(N_MFCC)]
)


def extract_features(samples: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Return a fixed-length feature vector for a window of audio.

    Pure-numpy; safe on silent / empty input (returns zeros).
    """
    x = _to_mono_float(samples)
    n = len(FEATURE_NAMES)
    if x.size == 0 or float(np.max(np.abs(x))) < 1e-7:
        # Silence: zeros everywhere except we still report it honestly.
        return np.zeros(n, dtype=np.float64)

    frames = _frame_signal(x, FRAME_LEN, FRAME_HOP)
    n_fft = FRAME_LEN
    pspec = _power_spectrum(frames, n_fft)            # (frames, bins)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)        # (bins,)
    eps = 1e-10

    # Time-domain
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + eps)
    sign = np.sign(frames)
    sign[sign == 0] = 1
    zcr = np.mean(np.abs(np.diff(sign, axis=1)) > 0, axis=1)

    # Spectral
    pmag = pspec + eps
    psum = np.sum(pmag, axis=1, keepdims=True)
    centroid = np.sum(freqs[None, :] * pmag, axis=1) / psum[:, 0]
    cumpow = np.cumsum(pmag, axis=1)
    rolloff_thresh = 0.85 * cumpow[:, -1]
    rolloff_idx = np.argmax(cumpow >= rolloff_thresh[:, None], axis=1)
    rolloff = freqs[rolloff_idx]
    geo = np.exp(np.mean(np.log(pmag), axis=1))
    arith = np.mean(pmag, axis=1)
    flatness = geo / (arith + eps)                    # 1 = noise-like, →0 = tonal
    dom_idx = np.argmax(pmag, axis=1)
    dom_freq = freqs[dom_idx]
    # Dominant-bin power relative to the mean bin power: large for tones,
    # ~1 for flat/noise-like spectra.
    peak_ratio = pmag[np.arange(pmag.shape[0]), dom_idx] / (arith + eps)

    # Energy distribution by band
    low_band = (freqs >= 200) & (freqs <= 700)        # tone band
    voice_band = (freqs >= 300) & (freqs <= 3400)     # telephony voice band
    total_e = np.sum(pmag) + eps
    low_ratio = float(np.sum(pmag[:, low_band]) / total_e)
    voice_ratio = float(np.sum(pmag[:, voice_band]) / total_e)

    # Cadence-ish: how much frame energy fluctuates (speech fluctuates, tones steady)
    energy_var_ratio = float(np.std(rms) / (np.mean(rms) + eps))

    # Targeted telephony tone energies (normalised)
    tone_feats = []
    for f in _TONE_FREQS:
        bin_i = int(np.argmin(np.abs(freqs - f)))
        lo = max(0, bin_i - 1)
        hi = min(len(freqs), bin_i + 2)
        tone_feats.append(float(np.mean(pmag[:, lo:hi]) / (arith.mean() + eps)))

    # MFCCs
    fb = _get_mel_fb(N_MELS, n_fft, sr)
    mel_e = np.log(pspec @ fb.T + eps)                # (frames, n_mels)
    mfcc = _dct(mel_e, N_MFCC)                         # (N_MFCC, frames)
    mfcc_mean = np.mean(mfcc, axis=1)
    mfcc_std = np.std(mfcc, axis=1)

    feats = [
        float(np.mean(rms)), float(np.std(rms)), float(np.max(rms)),
        float(np.mean(zcr)), float(np.std(zcr)),
        float(np.mean(centroid)), float(np.std(centroid)),
        float(np.mean(rolloff)),
        float(np.mean(flatness)), float(np.std(flatness)),
        float(np.mean(dom_freq)), float(np.std(dom_freq)),
        float(np.mean(peak_ratio)), float(np.max(peak_ratio)),
        low_ratio, voice_ratio,
        energy_var_ratio,
    ]
    feats += tone_feats
    feats += list(mfcc_mean)
    feats += list(mfcc_std)
    vec = np.asarray(feats, dtype=np.float64)
    vec[~np.isfinite(vec)] = 0.0
    return vec


# ── Result type ───────────────────────────────────────────────────────────────
@dataclass
class CPAResult:
    label: str                 # one of LABELS
    state: str                 # mapped app state (RINGING/CONNECTED/VOICEMAIL/FAILED)
    confidence: float          # 0..1
    proba: dict[str, float]    # full distribution
    source: str                # "model" or "heuristic"


# ── Rule-based fallback (used when no trained model is available) ─────────────
def _heuristic_classify(feats: np.ndarray) -> CPAResult:
    f = {name: feats[i] for i, name in enumerate(FEATURE_NAMES)}
    rms = f["rms_mean"]
    flatness = f["flatness_mean"]
    dom = f["dom_freq_mean"]
    peak_ratio = f["peak_ratio_mean"]
    energy_var = f["energy_var_ratio"]
    zcr = f["zcr_mean"]

    if rms < 1e-3:
        return CPAResult("SILENCE", LABEL_TO_STATE["SILENCE"], 0.6,
                         {"SILENCE": 1.0}, "heuristic")

    tonal = flatness < 0.25 and peak_ratio > 5.0
    if tonal:
        # Busy / reorder lives around 480+620; ringback around 440+480.
        if 560 <= dom <= 700:
            return CPAResult("BUSY", LABEL_TO_STATE["BUSY"], 0.55,
                             {"BUSY": 1.0}, "heuristic")
        if 380 <= dom <= 520:
            return CPAResult("RINGBACK", LABEL_TO_STATE["RINGBACK"], 0.55,
                             {"RINGBACK": 1.0}, "heuristic")
        if dom >= 900:
            return CPAResult("VOICEMAIL", LABEL_TO_STATE["VOICEMAIL"], 0.5,
                             {"VOICEMAIL": 1.0}, "heuristic")
        return CPAResult("RINGBACK", LABEL_TO_STATE["RINGBACK"], 0.4,
                         {"RINGBACK": 1.0}, "heuristic")

    # Non-tonal energy = speech of some kind. High variability + ZCR → live human.
    if energy_var > 0.45 and zcr > 0.04:
        return CPAResult("HUMAN", LABEL_TO_STATE["HUMAN"], 0.5,
                         {"HUMAN": 1.0}, "heuristic")
    return CPAResult("VOICEMAIL", LABEL_TO_STATE["VOICEMAIL"], 0.45,
                     {"VOICEMAIL": 1.0}, "heuristic")


# ── Public classifier ─────────────────────────────────────────────────────────
class CallProgressClassifier:
    """Loads the trained model (if present) and classifies audio windows."""

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or DEFAULT_MODEL_PATH
        self._model = None
        self._labels: list[str] = LABELS
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.model_path):
            return
        try:
            import joblib
            bundle = joblib.load(self.model_path)
            self._model = bundle["model"]
            self._labels = list(bundle.get("labels", LABELS))
        except Exception:
            self._model = None

    @property
    def has_model(self) -> bool:
        return self._model is not None

    def classify(self, samples: np.ndarray, sr: int = SAMPLE_RATE) -> CPAResult:
        feats = extract_features(samples, sr)
        if self._model is None:
            return _heuristic_classify(feats)
        try:
            proba = self._model.predict_proba(feats.reshape(1, -1))[0]
            idx = int(np.argmax(proba))
            label = self._labels[idx]
            dist = {self._labels[i]: float(proba[i]) for i in range(len(self._labels))}
            return CPAResult(label, LABEL_TO_STATE.get(label, "RINGING"),
                             float(proba[idx]), dist, "model")
        except Exception:
            return _heuristic_classify(feats)


# ── DOM + audio fusion ────────────────────────────────────────────────────────
# Confidence thresholds for letting the audio model override the DOM signal.
AUDIO_CONNECT_THRESHOLD = 0.62     # need solid confidence to declare a human pickup
AUDIO_VOICEMAIL_THRESHOLD = 0.60
AUDIO_BUSY_THRESHOLD = 0.70

_ACTIVE_DOM_STATES = {"DIALING", "RINGING", "CONNECTED", "CONNECTED_CTRL", "VOICEMAIL"}


def fuse_states(dom_state: str, audio: Optional[CPAResult]) -> str:
    """Combine the DOM-scraped state with the AI audio result.

    The DOM decides whether a call is *active at all* (the in-call UI is the
    ground truth for "a call exists").  When a call is active, the audio model
    disambiguates the cases the DOM gets wrong — ringback misread as voicemail,
    or a stray timer misread as a live answer — but only when it is confident,
    so an unavailable/uncertain audio stream never regresses behaviour.
    """
    dom = (dom_state or "IDLE").upper()

    # Not in a call → audio is irrelevant; trust the DOM.
    if dom not in _ACTIVE_DOM_STATES:
        return dom
    if audio is None:
        return dom

    label, conf = audio.label, audio.confidence

    # Busy / reorder tone = the number is unavailable, end fast.
    if label == "BUSY" and conf >= AUDIO_BUSY_THRESHOLD:
        return "FAILED"

    # Confident human pickup → CONNECTED, even if the DOM still shows ringing.
    if label == "HUMAN" and conf >= AUDIO_CONNECT_THRESHOLD:
        return "CONNECTED"

    # Confident voicemail → VOICEMAIL (beep/greeting), even if DOM lags.
    if label == "VOICEMAIL" and conf >= AUDIO_VOICEMAIL_THRESHOLD:
        return "VOICEMAIL"

    # Audio still hears ringback or silence → it is NOT answered yet.
    # Block premature CONNECTED/VOICEMAIL coming from a flaky DOM read.
    if label in ("RINGBACK", "SILENCE") and conf >= AUDIO_CONNECT_THRESHOLD:
        if dom in ("CONNECTED", "CONNECTED_CTRL", "VOICEMAIL"):
            return "RINGING"

    return dom
