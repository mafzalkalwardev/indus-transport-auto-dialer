# AMD testing guide

## Unit tests

```powershell
cd "D:\Auto Dialer"
python -m pytest tests/ -q
python run_full_test.py
```

## Live smoke (owned test numbers)

```powershell
python scripts/live_call_smoke.py --numbers +15127616455
```

Watch `detection_time_ms` in slot cards and JSON report under `logs/`.

## External extension evidence tests

```powershell
python -m pytest tests/test_external_evidence.py tests/test_external_evidence_integration.py tests/test_external_evidence_fixtures.py -q
```

## Config keys

| Key | Purpose |
|-----|---------|
| `amd_mode` | `heuristic`, `hybrid`, `whisper`, or `off` |
| `amd_early_decision_ms` | Target early decision window |
| `amd_max_decision_ms` | Max classification window |
| `enable_ai_audio` | WASAPI loopback fusion (capped on 8GB) |
| `predictive_mode` | Dynamic dials via `src/pacing/engine.py` |
| `websocket_enabled` | Supervisor wallboard on port 8765 |
| `external_detector_enabled` | Enable external extension evidence (default `false`) |
| `external_detector_mode` | `prototype_a` (live) or `prototype_b` (offline/testing) |
| `external_detector_merge_mode` | `evidence_only` (default and only supported) |
| `external_detector_timeout_ms` | Connection timeout for backend (default 1500) |
| `external_detector_fail_open` | Continue local detection if external fails (default `true`) |
| `external_detector_debug` | Verbose external provider logging (default `true`) |
| `external_detector_backend_url` | Backend host for Prototype A (default `127.0.0.1`) |
| `external_detector_backend_port` | Backend port for Prototype A (default `8787`) |

## Hardware tiers

- **8GB agent PC**: 1 line, `amd_mode=heuristic`, audio optional
- **16GB team server**: 2–3 lines, beep + predictive lite
- **32GB dialer**: whisper fallback + WebSocket dashboard
