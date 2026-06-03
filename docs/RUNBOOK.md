# Indus Transports Auto Dialer — Operations Runbook

## Log files

| File | Purpose |
|------|---------|
| `logs/dialer.log` | Watchdog restarts, retries, errors (rotating, 5 × 2 MB) |
| `logs/crm.sqlite3` | Users, call history |
| `logs/call_logs.csv` | Exported call log (if used) |

## Client vs administrator PC

- **Administrator:** `deployment_mode` is `admin` (default). Full Settings + Administration.
- **Client:** `deployment_mode` is `client` in `dialer_config.json`. Agent sign-in only; export package from **Administration → Export client package**.

## Google Voice not ready

1. **Settings** → select line → **Connect account** (complete 2FA if prompted).
2. Confirm `chrome_profiles/<profile>/.gv_session_ok` exists after login.
3. Check `data/gv_accounts.json` has email and password for automatic login.
4. Restart the app after profile changes.

## Terminal messages (usually safe to ignore)

| Message | Meaning |
|---------|---------|
| `Failed to create GLES3 context` / `disable-gpu` | Normal on Windows when GPU is disabled so login pages render. Dialing still works. |
| `Release of profile requested but WebEnginePage still not deleted` | Fixed in current builds — restart the app fully (close all instances) if you still see this after Ctrl+C. |
| `Unable to move the cache: Access is denied` | Another copy of the app or a zombie QtWebEngine process holds the cache. Close all Auto Dialer windows, end **QtWebEngineProcess** in Task Manager, then restart. |
| `Failed to resolve address for stun.l.google.com` | Temporary network/DNS issue for WebRTC; retry or check internet. |
| `QSystemTrayIcon::setVisible: No Icon set` | Harmless Qt warning; does not affect dialing. |

## Listen window is blank (white panel)

1. Click **Refresh view** in the Listen window (does not end the call).
2. Close Listen, wait 2 seconds, open **Listen** again.
3. Confirm Windows sound output device and volume; Google Voice audio plays through system speakers.
4. If still blank after restart of the app, use **Settings → Connect account** once for that line.

## Slot stuck or “Recovering line”

The **watchdog** restarts a line when:

- No heartbeat for ~45 seconds during a call
- Stuck in Dialing/Ringing/On call for ~90 seconds (config: `watchdog_stuck_state_sec`)
- WebEngine memory over limit (config: `slot_memory_limit_mb`, default 700 MB total)
- More than `slot_recycle_after_calls` completed calls on one line (default 75)

**What to do:**

1. Let recovery finish (status bar: “Line N recovering”).
2. Check `logs/dialer.log` for the reason.
3. If repeats every minute: reduce **Lines at once**, sign in again for that GV account, or reboot the PC.
4. Tune `dialer_config.json` if needed (see below).

## Failed numbers and retries

- Each number is retried up to **3** times with backoff **5s → 15s → 45s** (`max_retries`, `retry_backoff_sec`).
- After max retries, status **FAILED** is logged in CRM/Logs.
- Retries run automatically; do not stop the campaign unless necessary.

## Long campaigns (1000+ numbers, 8 slots)

1. Generate list: `python scripts/generate_load_test_list.py`
2. Optional RAM monitor: `python scripts/load_test_monitor.py` (separate terminal)
3. Follow [LOAD_TEST.md](LOAD_TEST.md) checklist
4. Between campaigns, **Stop** dialing (clears HTTP cache per line)

## Configuration (`dialer_config.json`)

```json
{
  "max_retries": 3,
  "retry_backoff_sec": [5, 15, 45],
  "watchdog_heartbeat_timeout_sec": 45,
  "watchdog_stuck_state_sec": 90,
  "slot_memory_limit_mb": 700,
  "slot_recycle_after_calls": 75,
  "watchdog_check_interval_sec": 5
}
```

## Deferred features (not in this build)

- **Screenshot/OCR** call-state detection — not used; state is detected via JavaScript in the embedded browser.
- **Call recording** — not implemented; add only if compliance requires it after stability testing.

## Support checklist

- [ ] `logs/dialer.log` last 50 lines
- [ ] Number of active GV lines vs `n_slots`
- [ ] Windows version and available RAM
- [ ] Whether issue happens on admin PC or client package only
