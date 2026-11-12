# AMD / Pacing Test Guide

How to confirm that the dialer behaves correctly on an AMD Ryzen workstation, and how to tune
the pacing so calls are not flagged by Google Voice.

AMD-specific behavior in this app comes from the embedded Chromium browser
(`QWebEngineView` / `PyQt6-WebEngine`) and from WebRTC audio capture. Both are sensitive to
CPU scheduler and memory pressure, so pacing and slot count need to be validated on the
machine that will actually run the campaign — not on a faster development box.

## Prerequisites

- An AMD Ryzen workstation (any generation), Windows 10 or 11
- One Google Voice account per simultaneous line
- Test numbers you own or have consent to call
- `pip install psutil` (already in `requirements.txt`)
- `pip install -r requirements.txt`

## 1. Confirm the environment

```bash
python -c "import platform,psutil;print(platform.processor());print(psutil.virtual_memory())"
```

Check the reported CPU and total RAM. Note the values — you will compare them against the
metrics collected in step 4.

## 2. Configure the test

In `dialer_config.json` (or in **Settings** before you start):

```json
{
  "n_slots": 4,
  "call_timeout": 45,
  "cooldown": 2.0,
  "dial_stagger_sec": 1.2,
  "voicemail_hangup_sec": 4,
  "max_retries": 3,
  "retry_backoff_sec": [5, 15, 45],
  "slot_memory_limit_mb": 700,
  "slot_recycle_after_calls": 75,
  "enable_ai_audio": true,
  "live_debug_mode": false
}
```

What these control:

| Setting | Effect |
|---------|--------|
| `n_slots` | Simultaneous lines. On an 8 GB Ryzen, start at 4, not 8 |
| `cooldown` | Base seconds between calls on a slot |
| `dial_stagger_sec` | Offset between starting each slot, so lines do not dial simultaneously |
| `call_timeout` | Seconds before an unanswered call is marked no answer |
| `voicemail_hangup_sec` | Seconds of voicemail before hanging up |
| `slot_memory_limit_mb` | Total WebEngine memory budget before the watchdog recycles slots |
| `slot_recycle_after_calls` | Completed calls on one line before it is recycled |
| `live_debug_mode` | Prints `[CALL DEBUG]` blocks for each call — turn on only while debugging |

Pacing is randomised between `cooldown_min` and `cooldown_max` (defaults 2 s and 4 s) on top
of the base `cooldown`, so calls do not fall into a fixed pattern.

## 3. Run the test

1. Generate the list: `python scripts/generate_load_test_list.py`
2. Optional RAM monitor, in a second terminal: `python scripts/load_test_monitor.py`
3. `python autodialer_gui.py`
4. **Dialer** → browse to `phones_load_1000.xlsx` → **Load contacts**
5. Set **Lines at once** to your `n_slots` value
6. **Start dialing** and let it run at least 2 hours

For the full checklist and pass/fail criteria, see [LOAD_TEST.md](LOAD_TEST.md).

## 4. Collect the numbers

`logs/load_test_metrics.csv` gets a row every 5 minutes:

| Column | Meaning |
|--------|---------|
| `timestamp` | When the sample was taken |
| `webengine_mb` | Total memory used by all Chromium processes |
| `system_ram_percent` | System RAM in use, as a percentage |
| `system_ram_used_mb` | System RAM in use, in MB |

`logs/dialer.log` records watchdog restarts, retries, and errors.

## 5. Read the results against your CPU

On an 8 GB Ryzen, treat these as the expected ceiling:

- WebEngine memory stays under **2 GB total** across all slots
- System RAM stays under **85%**
- Watchdog restarts stay under **10 per hour**
- A slot is not stuck in "Recovering line" more than once every few minutes

If WebEngine memory climbs steadily instead of sawtoothing around a ceiling, the slot
recycle is not firing — lower `slot_memory_limit_mb` or `slot_recycle_after_calls`.

## 6. Tune for the CPU

If calls are flagged or the system struggles, change one thing at a time and re-test:

| Symptom | Change |
|---------|--------|
| Calls flagged as automated | Raise `cooldown` and `dial_stagger_sec` |
| Slots stuck in "Recovering line" | Lower `n_slots`, then raise `watchdog_stuck_state_sec` |
| Memory climbs without recovering | Lower `slot_memory_limit_mb` or `slot_recycle_after_calls` |
| FAILED rate above 5% | Lower `n_slots`, check line health, confirm the watchdog is not recycling during calls |
| Listen window drops audio | Disable `enable_ai_audio` and confirm system audio output |

For a full campaign procedure, see [LOAD_TEST.md](LOAD_TEST.md). For slot recovery behavior,
see the runbook section on stuck slots in [RUNBOOK.md](RUNBOOK.md).

## Notes

- This build does not use OCR or call recording.
- The AI audio path needs a loopback capture device. Run
  `python scripts/audio_device_test.py` to confirm it reports `AI Audio: ON`.
