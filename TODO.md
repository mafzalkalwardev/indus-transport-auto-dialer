# TODO

## Call-state + voicemail/human pipeline fixes

- [x] Step 1: Identify ringing hangup bug location in `src/gv_controller.py` and fix policy so ringing never triggers voicemail/failed/hangup before timeout.

- [ ] Step 2: Enforce VICIdial-style state pipeline mapping (IDLE/DIALING/RINGING/CONNECTED/CLASSIFYING_AUDIO/HUMAN_DETECTED/VOICEMAIL_DETECTED/BUSY/NO_ANSWER/FAILED/ENDED) in controller glue.

- [ ] Step 3: Add missing timestamps (dialed_at/ringing_started_at/connected_at) and ensure they feed call-logging.

- [ ] Step 4: Improve per-call structured logging to include required fields exactly once per terminal state.

- [ ] Step 5: Ensure voicemail detector only runs after CONNECTED evidence and never during ringing (confirm in `src/local_call_detector.py`; adjust if needed).

- [x] Step 6: Add/update unit tests for the required edge cases.

- [x] Step 8: Run `pytest` and fix any regressions (40+ tests passing).

- [ ] Step 2: Enforce full VICIdial-style state pipeline mapping in UI labels only (engine already fused).

- [ ] Step 3: Add missing timestamps (dialed_at/ringing_started_at/connected_at) and ensure they feed call-logging.

- [ ] Step 4: Improve per-call structured logging to include required fields exactly once per terminal state.

- [ ] Step 9: Commit when ready: "Fix call state detection and human voicemail classification"

