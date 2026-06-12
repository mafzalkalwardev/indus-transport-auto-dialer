# GitHub repository review (for Indus Transports Auto Dialer)

Your dialer already uses **embedded Google Voice (QWebEngine) + DOM evidence + local audio fusion** with **40 automated tests**. Below is how the repos you listed relate to this project.

## Verdict summary

| Repo | Useful for this dialer? | Why |
|------|-------------------------|-----|
| **SeleniumHQ/selenium** | No (avoid) | You moved off Selenium to PyQt WebEngine. Re-adding Selenium adds process overhead and the same DOM fragility. |
| **scrapy/scrapy** | No | Web crawling framework, not live call control. |
| **mahimailabs/voicegateway** | No (different product) | LiveKit voice-agent gateway — for building your own telephony stack, not controlling Google Voice web UI. |
| **mahimairaja/voiceai** | Reference only | Curated links for Voice AI agents; good reading, not a drop-in library for GV. |
| **mahimailabs/openrtc-runtime** | No | Multi-agent LiveKit worker runtime — not GV integration. |
| **gradio-app/fastrtc** | Maybe later | WebRTC helpers if you ever leave GV and run your own RTC stack. |
| **openvinotoolkit/openvino** | Maybe later | On-device audio ML inference if you want a heavier audio-only AMD model; you already have `local_call_detector.py`. |
| **dioptx/google_aind_Part_of_Speech_Tagging** | No | 2019 NLP homework; unrelated. |
| **langchain-ai/langchain** | No | Agent orchestration; does not detect GV call states. |
| **numpy, psf/requests, pallets/flask** | Already standard | General Python stack; only use if you add a remote API dashboard. |
| **react, vue, next.js, bootstrap** | No | You ship a PyQt desktop app, not a web frontend. |

## What you already have (better fit than most listed repos)

```
Google Voice page (QWebEngine)
        │
        ├─► JS evidence (_JS_DETECT_STATE) ──► CallStateEngine
        │
        └─► System audio monitor ──► local_call_detector (VAD, ringback, beep, greeting)
                    │
                    └─► Fused decision (ringing / human / voicemail / no-answer / busy)
```

Run tests anytime:

```bash
python -m pytest tests/ -v
```

Live smoke (owner numbers only):

```bash
python scripts/live_call_smoke.py --help
python scripts/audio_device_test.py
```

## If detection still misclassifies on your PC

1. Run `python scripts/audio_device_test.py` — confirm loopback/VAD works.
2. Enable live debug monitor on a line (Listen → debug) and watch `detection_update` fields.
3. Do **not** replace DOM detection with OCR or Selenium; extend `_JS_DETECT_STATE` selectors instead.
4. Consider OpenVINO **only** if you want a dedicated offline audio classifier **in addition to** current fusion — not as a replacement.

## Repos worth watching (not integrating now)

- **voiceai** (awesome list) — patterns for consent, recording, agent design.
- **openvino** — if you later add a small ONNX voicemail/human model on Windows CPU.

Everything else in the list is general dev tooling or a different architecture (LiveKit agents, web SPAs, financial bots).
