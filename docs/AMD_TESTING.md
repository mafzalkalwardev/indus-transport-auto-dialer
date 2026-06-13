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

## Config keys

| Key | Purpose |
|-----|---------|
| `amd_mode` | `heuristic`, `whisper`, or `off` |
| `amd_early_decision_ms` | Target early decision window |
| `amd_max_decision_ms` | Max classification window |
| `enable_ai_audio` | WASAPI loopback fusion (capped on 8GB) |
| `predictive_mode` | Dynamic dials via `src/pacing/engine.py` |
| `websocket_enabled` | Supervisor wallboard on port 8765 |

## Hardware tiers

- **8GB agent PC**: 1 line, `amd_mode=heuristic`, audio optional
- **16GB team server**: 2–3 lines, beep + predictive lite
- **32GB dialer**: whisper fallback + WebSocket dashboard
