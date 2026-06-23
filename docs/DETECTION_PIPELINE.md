# Call Detection Pipeline

The dialer uses a staged detector, not a chat model:

```text
Call dialed
-> detect dialing/ringing from DOM + ringback cadence
-> detect answer evidence from DOM controls/timer + audio change
-> run VAD over captured audio
-> score human vs voicemail from transcript/timing/audio patterns
-> external extension evidence (optional, evidence-only) merged before scoring
-> final FSM decision
```

## Stages

1. **Basic call stage**
   - Ringing: Google Voice calling/ringing UI, ringback cadence, no answer evidence.
   - Connected/answered pending: ringback stops and speech/noise/control evidence appears.
   - Busy: busy tone cadence.
   - Failed: browser/page technical failure.
   - No answer: only after `call_timeout`/`max_ring_seconds`.

2. **VAD**
   - Preferred: `webrtcvad` from `webrtcvad-wheels`.
   - Fallback: local RMS/zero-crossing heuristic.
   - Debug fields: `vad_backend`, `vad_confidence`.

3. **Human detector**
   - Short greeting under 2.5 seconds.
   - Transcript keywords: `hello`, `hi`, `yes`, `who is this`, `speaking`.
   - Speech/noise in the first 5-8 seconds after answer.

4. **Voicemail detector**
   - Never runs while still ringing.
   - Requires answer evidence and at least 7 seconds after answer.
   - Requires at least two strong signals: long scripted greeting, voicemail keyword, beep, machine pattern, or DOM voicemail cue.

5. **External extension evidence (optional)**
   - Chrome extension prototypes may provide live transcript + label hints.
   - Prototype A (FastAPI + Deepgram) is the preferred live provider.
   - Prototype B (whisper.cpp + rules) is the offline/testing fallback.
   - All extension outputs are **evidence only**: they boost local scoring but never bypass the DOM-first answer timer, voicemail safe window, or human audio gate.
   - Disabled by default. Enable via `dialer_config.json`:
     - `"external_detector_enabled": true`
     - `"external_detector_mode": "prototype_a"` (or `"prototype_b"`)

## Dataset Layout

Runtime samples should go under ignored local folders:

```text
data/detection_samples/
  ringing/
  human_pickup/
  voicemail/
  busy/
  silence/
  beep/
```

Start with 20-30 clean examples per class, then grow to 50-100. Keep labels honest: do not mix early ringing audio into voicemail samples.

## Model Progression

1. Rule-based detector using timing, VAD, keywords, beep, cadence.
2. Local transcript input from Whisper if needed.
3. Small classifier using MFCC/audio features + transcript text + speech duration + silence gaps.
4. Optional external extension evidence (Prototype A/B) merged as evidence-only.

Cloud transcription such as Groq/Deepgram can be wired later behind config, but the current app remains local-first and continues without cloud APIs.
