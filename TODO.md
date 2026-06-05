# TODO - Fix false voicemail detection

- [ ] Step 1: Inspect current local detector + tests (done: read local_call_detector.py and tests/test_call_detection.py)
- [ ] Step 2: Implement ANSWERED_PENDING safe window + human-first rules in `src/local_call_detector.py`
- [ ] Step 3: Implement stricter VOICEMAIL confirmation (2-of-5) + stability cycles + confidence gating in `src/local_call_detector.py`
- [ ] Step 4: Add debug logs per state decision in `src/local_call_detector.py`
- [ ] Step 5: Extend audio feature expectations (duck-typed optional fields) in detector and update tests’ DummyAudio
- [ ] Step 6: Update/extend unit tests per required scenarios in `tests/test_call_detection.py`
- [ ] Step 7: Run `pytest -q` and adjust thresholds/tests to pass

