"""Tests for the AI call-progress classifier and DOM/audio fusion logic."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.call_audio_ai import (  # noqa: E402
    FEATURE_NAMES,
    SAMPLE_RATE,
    WINDOW_SEC,
    CallProgressClassifier,
    CPAResult,
    extract_features,
    fuse_states,
)

SR = SAMPLE_RATE
N = int(WINDOW_SEC * SR)
_T = np.arange(N) / SR


# ── synthetic call-progress audio ─────────────────────────────────────────────
def _tone(freqs, amp=0.3):
    sig = np.zeros(N)
    for f in freqs:
        sig += np.sin(2 * np.pi * f * _T)
    return amp * sig / len(freqs)


def ringback():
    return _tone([440, 480])


def busy():
    seg = np.concatenate([
        _tone([480, 620])[:int(0.5 * SR)], np.zeros(int(0.5 * SR))])
    return np.tile(seg, 2)[:N]


def beep():
    out = np.zeros(N)
    out[int(0.2 * SR):int(0.6 * SR)] = 0.4 * np.sin(2 * np.pi * 1000 * _T[:int(0.4 * SR)])
    return out


def silence():
    return 0.001 * np.random.default_rng(0).standard_normal(N)


# ── feature extraction ────────────────────────────────────────────────────────
def test_feature_vector_length_matches_names():
    feats = extract_features(ringback(), SR)
    assert feats.shape == (len(FEATURE_NAMES),)


def test_features_are_finite_and_safe_on_empty():
    assert np.all(np.isfinite(extract_features(ringback(), SR)))
    assert np.all(np.isfinite(extract_features(np.array([]), SR)))
    assert np.all(extract_features(np.zeros(N), SR) == 0.0)


def test_ringback_is_tonal_low_flatness():
    feats = {n: v for n, v in zip(FEATURE_NAMES, extract_features(ringback(), SR))}
    # A pure dual-tone is highly tonal → low spectral flatness, strong peak.
    assert feats["flatness_mean"] < 0.3
    assert feats["peak_ratio_mean"] > 3.0


# ── trained model ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def clf():
    return CallProgressClassifier()


def test_model_artifact_present(clf):
    # The committed model should load; if this fails the model wasn't shipped.
    assert clf.has_model, "trained model models/call_progress_model.joblib not loaded"


def test_model_classifies_call_progress_tones(clf):
    assert clf.classify(ringback(), SR).label == "RINGBACK"
    assert clf.classify(busy(), SR).label == "BUSY"
    assert clf.classify(silence(), SR).label == "SILENCE"
    assert clf.classify(beep(), SR).label == "VOICEMAIL"


def test_label_to_state_mapping(clf):
    assert clf.classify(ringback(), SR).state == "RINGING"
    assert clf.classify(busy(), SR).state == "FAILED"
    assert clf.classify(beep(), SR).state == "VOICEMAIL"


def test_classifier_falls_back_when_model_missing():
    c = CallProgressClassifier(model_path="/nonexistent/model.joblib")
    assert not c.has_model
    res = c.classify(ringback(), SR)
    assert isinstance(res, CPAResult)
    assert res.source == "heuristic"
    assert res.label in ("RINGBACK", "BUSY")  # tonal → a tone class


# ── fusion logic ──────────────────────────────────────────────────────────────
def _r(label, conf):
    return CPAResult(label, {"RINGBACK": "RINGING", "HUMAN": "CONNECTED",
                             "VOICEMAIL": "VOICEMAIL", "BUSY": "FAILED",
                             "SILENCE": "RINGING"}[label], conf, {}, "model")


def test_fusion_idle_ignores_audio():
    # No active call → audio must never invent a state.
    assert fuse_states("IDLE", _r("HUMAN", 0.99)) == "IDLE"
    assert fuse_states("ENDED", _r("VOICEMAIL", 0.99)) == "ENDED"


def test_fusion_none_audio_returns_dom():
    assert fuse_states("RINGING", None) == "RINGING"
    assert fuse_states("CONNECTED", None) == "CONNECTED"


def test_fusion_human_promotes_to_connected():
    # DOM still says ringing, but audio confidently hears a person.
    assert fuse_states("RINGING", _r("HUMAN", 0.9)) == "CONNECTED"


def test_fusion_voicemail_detected():
    assert fuse_states("RINGING", _r("VOICEMAIL", 0.8)) == "VOICEMAIL"


def test_fusion_busy_fails_fast():
    assert fuse_states("RINGING", _r("BUSY", 0.85)) == "FAILED"


def test_fusion_blocks_false_connected_when_audio_hears_ringback():
    # The key bug fix: a flaky DOM "CONNECTED" must not stick while we still
    # hear ringback / silence.
    assert fuse_states("CONNECTED", _r("RINGBACK", 0.9)) == "RINGING"
    assert fuse_states("VOICEMAIL", _r("SILENCE", 0.9)) == "RINGING"


def test_fusion_low_confidence_audio_does_not_override():
    # Below threshold → trust the DOM.
    assert fuse_states("RINGING", _r("HUMAN", 0.4)) == "RINGING"
    assert fuse_states("CONNECTED", _r("VOICEMAIL", 0.3)) == "CONNECTED"
