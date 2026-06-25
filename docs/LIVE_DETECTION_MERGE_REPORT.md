# Live Detection Merge Report

## Final readiness status

- dry-run supported: yes
- real live smoke tested: no
- approved test numbers required: yes
- backend required: yes, Prototype A FastAPI on 127.0.0.1:8787; Prototype B optional on localhost:3100
- GUI toggle available: no
- untracked prototype folder decision: do not commit; use separate backend repo or add after secret scan
- safe local test commands:
  - python scripts/live_call_smoke_dry_run.py --dry-run
  - python scripts/external_detector_health.py
- rollback command: git revert --no-commit HEAD && git reset
- config kill switch: set "external_detector_enabled": false in dialer_config.json

## Evidence-layer merge summary

LocalCallDetector remains the final arbiter. External detector outputs are evidence only. No direct final-state override from Prototype A or Prototype B. Voicemail safe-window, answer timer, confirmation cycles, and final-state-once rules are unchanged.

## Backend dependency note

The untracked folder voicemail_vs_human_detection/ is NOT required by the shipped Python package. Adapters reference only:
- Prototype A: ws://127.0.0.1:8787/ws/amd-audio
- Prototype B: localhost:3100

If you later integrate that prototype code:
A) commit it after secret scan/cleanup, or
B) move it to a separate external backend repo and document setup.