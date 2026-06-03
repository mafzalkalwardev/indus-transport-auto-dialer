# Load test procedure (1000 numbers, 8 slots, 2+ hours)

Use this before production campaigns at scale.

## Prerequisites

- Administrator PC with all GV lines signed in (Settings → each line **Ready**)
- Target hardware (same class as production)
- Test numbers you **own or have consent** to call
- `pip install psutil` (in `requirements.txt`)

## 1. Generate the contact list

```bash
python scripts/generate_load_test_list.py
```

Creates `phones_load_1000.xlsx` in the project root (cycles your test numbers from `phones_test.xlsx` or built-in samples).

## 2. Configure the app

In `dialer_config.json` (or Settings before start):

```json
{
  "n_slots": 8,
  "call_timeout": 45,
  "cooldown": 2.0,
  "voicemail_hangup_sec": 3,
  "slot_memory_limit_mb": 700,
  "slot_recycle_after_calls": 75
}
```

## 3. Start RAM monitor (optional)

In a second terminal:

```bash
python scripts/load_test_monitor.py
```

Writes `logs/load_test_metrics.csv` every 5 minutes (timestamp, total WebEngine MB, system RAM %).

## 4. Run the campaign

1. `python autodialer_gui.py`
2. **Dialer** → browse to `phones_load_1000.xlsx` → **Load contacts**
3. Set **Lines at once** = 8
4. **Start dialing**
5. Run at least **2 hours** (or until list completes)

## 5. Record results

| Metric | Target | Your run |
|--------|--------|----------|
| Numbers completed | ≥ 95% of 1000 | |
| FAILED after retries | < 5% | |
| Watchdog restarts | < 10 per hour | |
| WebEngine RAM (peak) | < 2 GB total | |
| Manual intervention | 0 | |

Check:

- `logs/dialer.log` — restarts and retries
- `logs/load_test_metrics.csv` — memory trend
- In-app **Logs** tab — FAILED count

## 6. Pass / fail

**Pass:** Campaign finishes or >95% dialed with no sustained slot stuck state; RAM stable or periodic recycle only.

**Fail:** Repeated stuck lines, runaway RAM, or >10% FAILED — reduce slots, lower `slot_recycle_after_calls`, or increase `watchdog_stuck_state_sec` and re-test.

## Notes

- This build does **not** use OCR or call recording.
- For real load, replace generated numbers with your licensed test pool in the Excel file.
