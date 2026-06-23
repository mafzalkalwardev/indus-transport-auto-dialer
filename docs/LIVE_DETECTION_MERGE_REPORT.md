# Live Detection Merge Report

## Architecture Summary

The Auto Dialer’s existing Python detection engine remains the **final arbiter** of call state.

- `LocalCallDetector` (in `src/local_call_detector.py`) continues to own:
  - DOM-first answer timer
  - Voicemail safe window and confirmation cycles
  - Human audio gate
  - Final state emission (once per call)
- Chrome extension outputs are treated as **evidence only** and never directly set `HUMAN`, `VOICEMAIL`, `BUSY`, `ENDED`, `FAILED`, or `NO_ANSWER`.

### Provider Roles

| Provider | Mode | Backend | Purpose |
|----------|------|---------|---------|
| **Prototype A** | Live (preferred) | FastAPI + Deepgram WebSocket at `ws://127.0.0.1:8787/ws/amd-audio` | Real-time tab audio streaming and transcript classification |
| **Prototype B** | Offline / testing | Node.js / whisper.cpp at `http://localhost:3100` | Offline experiments, fixture replay, regression testing |

### Evidence Flow

```text
Extension/Backend
    │
    ▼
PrototypeAAdapter  or  PrototypeBAdapter
    │
    ▼
ExternalEvidenceManager  (provider health, timeouts, fail-open)
    │
    ▼
ExternalEvidenceMapper  (normalize labels → detector-safe fields)
    │
    ▼
LocalCallDetector.decide()  (merge into transcript/human/voicemail/busy signals)
    │
    ▼
Safety rails enforced:
  • DOM-first answer clock
  • Voicemail safe window
  • Human audio gate
  • Single final-state emission
    │
    ▼
CallDecisionEngine  (fuse with FSM)
    │
    ▼
GVController  (emit debug + state change)
    │
    ▼
Auto Dialer GUI  (slot cards show external provider status)
```

## Files Changed

### New files
- `src/detection/external_evidence.py`
- `src/detection/external_evidence_mapper.py`
- `src/detection/providers/__init__.py`
- `src/detection/providers/prototype_a_adapter.py`
- `src/detection/providers/prototype_b_adapter.py`
- `src/detection/external_evidence_manager.py`
- `tests/test_external_evidence.py`
- `tests/test_external_evidence_integration.py`
- `tests/test_external_evidence_fixtures.py`
- `docs/LIVE_DETECTION_MERGE_REPORT.md`

### Modified files
- `src/detection/__init__.py`
- `src/local_call_detector.py`
- `src/call_decision_engine.py`
- `src/call_state_detector.py`
- `src/gv_controller.py`
- `autodialer_gui.py`
- `dialer_config.example.json`
- `docs/DETECTION_PIPELINE.md`
- `docs/AMD_TESTING.md`
- `docs/RUNBOOK.md`
- `scripts/live_call_smoke.py`

## Config Keys Added

| Key | Default | Purpose |
|-----|---------|---------|
| `external_detector_enabled` | `false` | Master switch for external evidence ingestion |
| `external_detector_mode` | `"prototype_a"` | Choose live (`prototype_a`) or offline/testing (`prototype_b`) |
| `external_detector_merge_mode` | `"evidence_only"` | Currently the only supported mode; extensions never override final state |
| `external_detector_timeout_ms` | `1500` | Backend connection / probe timeout |
| `external_detector_fail_open` | `true` | Continue local detection if external backend is unreachable |
| `external_detector_debug` | `true` | Log external provider connect/disconnect and evidence accept/ignore reasons |
| `external_detector_backend_url` | `"127.0.0.1"` | Host for Prototype A backend |
| `external_detector_backend_port` | `8787` | Port for Prototype A backend |

## Tests Run

```text
python -m pytest -q
# Result: 162 passed, 3 warnings

python -m pytest tests/test_external_evidence.py tests/test_external_evidence_integration.py tests/test_external_evidence_fixtures.py -q
# Result: 44 passed
```

### Test Coverage

- **Prototype A label mapping**: `human_picked`, `voicemail_detected`, `call_screening_prompt`, `busy_or_failed`, `still_ringing`, `ended`, `no_answer`, `unknown`
- **Prototype B label mapping**: `human`, `voicemail`, `busy`, `disconnected_or_failed`, `unknown_or_silence`, `unknown`
- **Safety rules**:
  - Extension says voicemail while DOM is still ringing → final state must NOT be VOICEMAIL
  - Extension says human before DOM answer evidence → answer clock must NOT start from extension alone
  - Repeated `voicemail_detected` after answer evidence → only becomes VOICEMAIL after safe window and confirmation cycles
  - Provider timeout/disconnect → detector continues safely
  - Final state emitted only once
- **Replay fixtures**: normal human hello, voicemail greeting, still ringing / no answer, busy, disconnected/failed, extension conflict (human then voicemail), websocket/provider failure

## Compile Checks

```text
python -m py_compile src/call_state_detector.py src/local_call_detector.py
python -m py_compile src/detection/external_evidence.py src/detection/external_evidence_mapper.py src/detection/providers/prototype_a_adapter.py src/detection/providers/prototype_b_adapter.py src/detection/external_evidence_manager.py src/detection/__init__.py src/call_decision_engine.py src/call_state_detector.py autodialer_gui.py scripts/live_call_smoke.py
# All passed
```

## Audio Device Test

```text
python scripts/audio_device_test.py
# AI Audio: ON
# recommended_device=31
```

## Live Smoke Test Status

- `python scripts/live_call_smoke.py --dry-run` — **not supported** (flag does not exist in the script).
- `python scripts/live_call_smoke.py --from-crm --crm-limit 2` — **not executed** because approved test numbers are not configured in this environment and the user instructed not to mass-dial random numbers.
- Dry-run behavior is available via `GVController` internal `dry_run_mode` config and can be exercised by setting `"dry_run_mode": true` in `dialer_config.json`.

## Known Limitations

1. **Extension browser compatibility**: Chrome MV3 extensions cannot be loaded into the Auto Dialer’s embedded `QWebEngineView`. The adapters connect to separate extension backend processes (FastAPI / Node.js) running locally.
2. **Prototype A WebSocket design**: Prototype A’s `/ws/amd-audio` is primarily an audio-ingest endpoint. The adapter connects as a second peer to receive state push. If the backend is not running or rejects extra peers, the adapter fails open and local detection continues.
3. **Prototype B is not a true live pipeline**: It operates on uploaded audio chunks or fixtures. For live use, a backend bridge would be required.
4. **No Ollama / LLM integration in this merge**: The architecture supports it as an additional evidence source, but it was not implemented in this pass.
5. **GUI external status**: Slot cards show `Ext AMD: off` when disabled, or `Ext prototype_a/b: <health> | <label> (<confidence>)` when enabled. This is a diagnostic summary, not a control.

## Rollback Instructions

To disable the external detector instantly:

1. Edit `dialer_config.json` (or via Settings in the GUI):
   ```json
   {
     "external_detector_enabled": false
   }
   ```
2. Restart the affected GVController lines, or fully restart the Auto Dialer.
3. `LocalCallDetector` will resume operating with DOM + audio only, exactly as before this merge.

To fully remove the merge (code rollback):

```bash
git revert --no-commit <merge-commit-sha>
git reset HEAD src/detection/external_evidence.py src/detection/external_evidence_mapper.py src/detection/providers/__init__.py src/detection/providers/prototype_a_adapter.py src/detection/providers/prototype_b_adapter.py src/detection/external_evidence_manager.py src/detection/__init__.py src/local_call_detector.py src/call_decision_engine.py src/call_state_detector.py src/gv_controller.py autodialer_gui.py dialer_config.example.json docs/DETECTION_PIPELINE.md docs/AMD_TESTING.md docs/RUNBOOK.md scripts/live_call_smoke.py tests/test_external_evidence.py tests/test_external_evidence_integration.py tests/test_external_evidence_fixtures.py docs/LIVE_DETECTION_MERGE_REPORT.md
git checkout -- .
```

Or simply cherry-pick the pre-merge commit to restore the original state.

## How to Disable External Detector Instantly

- **Via config file**: set `"external_detector_enabled": false` in `dialer_config.json`.
- **Via GUI**: (if Settings page exposes the toggle) uncheck external detector and apply.
- **At runtime without restart**: The `ExternalEvidenceManager` checks `enabled` on each poll tick. Setting it to `False` causes `get_latest()` to return `None` immediately, which means `LocalCallDetector` receives no external evidence and operates purely on local signals.

---

## Files Changed (for code review)

- `src/detection/external_evidence.py` — canonical `ExternalEvidence` dataclass
- `src/detection/external_evidence_mapper.py` — safe label mapping + audio-feature merge
- `src/detection/providers/prototype_a_adapter.py` — WebSocket client for Prototype A backend
- `src/detection/providers/prototype_b_adapter.py` — fixture replay / optional HTTP poller for Prototype B
- `src/detection/external_evidence_manager.py` — provider lifecycle, health, diagnostics
- `src/detection/__init__.py` — export new symbols
- `src/local_call_detector.py` — accept optional `external_evidence` in `decide()`
- `src/call_decision_engine.py` — orchestrate external manager + include evidence debug in output
- `src/call_state_detector.py` — forward `external_evidence` through facade
- `src/gv_controller.py` — init/start/stop external manager, poll for evidence, add diagnostics to `detection_update`
- `autodialer_gui.py` — slot-card label for external provider health and last label
- `dialer_config.example.json` — new config keys documented
- `docs/DETECTION_PIPELINE.md` — external evidence stage added to pipeline diagram
- `docs/AMD_TESTING.md` — config key table + external evidence test commands
- `docs/RUNBOOK.md` — rollback + disable instructions, developer checklist
- `scripts/live_call_smoke.py` — external evidence fields printed during `[CALL DEBUG]`
- `tests/test_external_evidence.py` — unit tests for dataclass and label mappings
- `tests/test_external_evidence_integration.py` — integration tests for safety rails
- `tests/test_external_evidence_fixtures.py` — replay fixtures and manager diagnostics
