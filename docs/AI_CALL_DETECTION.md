# AI Call-Progress Detection

This document describes the call-state detection used by the dialer and the trained AI audio module
that hardens it.

## Why

Previously the app decided Ringing / On-call / Voicemail / Picked-up **only** by scraping the Google
Voice web page. That is brittle:

- Voicemail announcement phrases (e.g. "the person you are calling…") also play during **ringback**,
  so a ringing call was sometimes labelled Voicemail.
- The `MM:SS` call-timer regex could match unrelated text on the page → a false **On-call**.
- Whole-page substring matches for "ringing"/"calling" are locale- and layout-dependent.

## Architecture — two layers, fused

```
  Google Voice page  ──►  DOM detector (_JS_DETECT_STATE)  ─┐
                                                            ├─► fuse_states() ─► call state
  Call audio (loopback) ─► CallAudioMonitor ─► classifier ─┘
```

### Layer 1 — DOM detector (`src/gv_controller.py`)
`_JS_DETECT_STATE` establishes whether a call is **active at all** (in-call/hang-up UI) and a first
guess at the stage. Hardened so that:
- Voicemail **strong** phrases ("record after the tone", "after the beep", …) are accepted any time,
  while **weak** phrases that also appear during ringback only count once ringing has stopped.
- The call timer is only read as On-call when ringing has stopped **and** the timer is past `00:00`.

### Layer 2 — AI audio classifier (`src/call_audio_ai.py`)
A trained Call-Progress-Analysis / Answering-Machine-Detection model. Pure-numpy feature extraction
(RMS energy, zero-crossing rate, spectral centroid/rolloff/flatness, dominant-frequency prominence,
targeted telephony-tone energies, and MFCCs) feeds a scikit-learn RandomForest. Classes:

| Label | Meaning | Mapped state |
|-------|---------|--------------|
| `RINGBACK` | Outbound ring tone | RINGING |
| `HUMAN` | A live person answered | CONNECTED |
| `VOICEMAIL` | Machine greeting or record beep | VOICEMAIL |
| `SILENCE` | Dead air (not progressed) | RINGING |
| `BUSY` | Busy / reorder (SIT) tone | FAILED |

numpy + scikit-learn (not PyTorch/TensorFlow) is deliberate: it is real-time on CPU and keeps the
PyInstaller EXE small.

### Fusion (`fuse_states`)
The DOM is authoritative about whether a call exists. When a call is active, the audio model
overrides the DOM **only when confident**:
- `HUMAN` ≥ 0.62 → CONNECTED (catches answers the page is slow to show).
- `VOICEMAIL` ≥ 0.60 → VOICEMAIL.
- `BUSY` ≥ 0.70 → FAILED (end fast).
- `RINGBACK`/`SILENCE` ≥ 0.62 blocks a premature CONNECTED/VOICEMAIL coming from a flaky page read.

If the audio stream is unavailable or uncertain, behaviour is exactly the (hardened) DOM detection —
so the AI layer can never regress dialing.

## Live capture (`src/call_audio_monitor.py`)
Captures the line's speaker output (loopback) in a background thread and classifies a ~1 s window
every 0.5 s, emitting a hint to the controller. Capture is best-effort: it tries `soundcard`
(cross-platform loopback) then `sounddevice`; if neither is available the monitor stays disabled and
the app logs "Audio AI: no capture backend — DOM only". Toggle with `audio_ai_enabled` in
`dialer_config.json`.

## Training data & model

`scripts/build_audio_dataset.py`:
- Synthesizes call-progress tones at the exact telephony standards — ringback (440+480 Hz / 425 Hz),
  busy (480+620 Hz), reorder/SIT (913.8/1370.6/1776.7 Hz), the voicemail beep (1000/1400 Hz) — with
  line-noise/gain augmentation.
- Downloads public-domain spoken-sentence recordings (Open Speech Repository, 8 kHz) for the HUMAN
  (short utterance + pause) and VOICEMAIL (continuous greeting) speech windows.

`scripts/train_call_model.py` trains a `StandardScaler → RandomForest` pipeline, reports 5-fold CV
and held-out accuracy + a confusion matrix, and writes `models/call_progress_model.joblib` (shipped
with the app).

Typical results: ~95% held-out accuracy. Tones (RINGBACK / BUSY / SILENCE) are ~perfect; the only
meaningful confusion is HUMAN ↔ VOICEMAIL, which is expected (both are speech) and is why live
voicemail also leans on the beep and the page text.

## Tests
`tests/test_call_audio_ai.py` covers feature extraction, the trained model on synthesized tones, the
heuristic fallback, and every branch of `fuse_states`. Run `pytest tests/`.
