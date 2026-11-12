# Google Voice Web Dialing Notes

Working notes on dialing Google Voice through the embedded browser, the failure modes seen in
practice, and where to look when something behaves oddly.

These notes describe the behaviour of the current build. They complement
[DETECTION_PIPELINE.md](DETECTION_PIPELINE.md), which covers how call state is classified.

## How dialing works

Each line is a hidden `QWebEngineView` with its own persistent Chromium profile under
`chrome_profiles/`. The app loads the Google Voice dialer UI in that view and drives it with
injected JavaScript.

1. **Sign in.** The app signs in automatically using the email and password in
   `data/gv_accounts.json`, unless the profile already holds a valid session.
2. **Ready state.** A line is **Ready** once its profile contains the `.gv_session_ok` marker
   and the dialer UI is loaded. A line that is not Ready cannot be used.
3. **Dial.** The app enters the number and clicks the call control in the embedded page.
4. **Detect.** The embedded page is polled for call state, and local audio capture is fused in
   when `enable_ai_audio` is on. See [DETECTION_PIPELINE.md](DETECTION_PIPELINE.md).
5. **Report.** Results land in the CRM and the Logs tab.

## Failure modes and fixes

### Google Voice not ready

1. **Settings** → select the line → **Connect account** (complete 2FA if prompted).
2. Confirm `chrome_profiles/<profile>/.gv_session_ok` exists after login.
3. Check `data/gv_accounts.json` holds the email and password for automatic login.
4. Restart the app after any profile change.

### A line will not dial

- Confirm the line shows **Ready** in the app.
- Open the browser panel for that line and look at the Google Voice UI. A sign-in page or a
  CAPTCHA means the session expired — reconnect the account and re-export the package if the
  client is on a delivered build.
- Check `logs/dialer.log` for the reason.

### The call connects but the app thinks nobody answered

The detector needs answer evidence from more than one signal. If a live call is being marked
no answer or voicemail, check:

- `call_timeout` is long enough for the ring cadence you expect.
- `enable_ai_audio` matches the hardware. Run `python scripts/audio_device_test.py`; a status
  of `AI Audio: NO BACKEND` means the loopback device cannot be captured, so only DOM
  evidence is available.
- The audio device index in `audio_device` still matches. Use
  `python scripts/audio_device_test.py --device <n> --seconds 2` to test a specific index.
- `live_debug_mode` is on, so `[CALL DEBUG]` blocks show `dom_state`, `audio_state`,
  `fused_state`, `confidence`, `reason`, and `should_hangup` for each call.

### Voicemail is misclassified as a human pickup

Voicemail detection requires answer evidence, at least 7 seconds after answer, and at least
two strong signals. If a recording is being treated as human:

- Confirm `voicemail_hangup_sec` is not so short that it cuts off the machine greeting.
- Confirm the microphone is not picking up the greeting twice, which can look like a second
  voice.

A short hello, a short speech burst, or a hello with background noise is deliberately treated
as human or answered-pending, never voicemail.

### Calls disconnect early

- `slot_memory_limit_mb` is reached and the watchdog recycles the slot mid-call. Raise it if
  the machine has headroom, or lower `n_slots`.
- `slot_recycle_after_calls` is reached after a completed call. That is intended behaviour.
- `watchdog_stuck_state_sec` is too tight for long ring cycles.

### Audio works but the Listen window is blank

1. Click **Refresh view** in the Listen window. This does not end the call.
2. Close Listen, wait 2 seconds, and open it again.
3. Confirm the Windows sound output device and volume. Google Voice audio plays through the
   system speakers.
4. After a full restart, use **Settings → Connect account** once for that line.

### The browser profile does not persist the session

- Each line needs its own profile directory. Copying a profile between lines mixes sessions.
- Profiles are copied into exported client packages. If they are missing on a client PC, the
  client must sign in manually, or the package must be re-exported with profiles included.
- Use `--no-profiles` on `scripts/prepare_client_install.py` when you do not want to hand
  over signed-in sessions at all.

## Terminal messages that are safe to ignore

| Message | Meaning |
|---------|---------|
| `Failed to create GLES3 context` / `disable-gpu` | Normal on Windows when GPU is disabled so login pages render. Dialing still works. |
| `Unable to move the cache: Access is denied` | Another copy of the app or a zombie QtWebEngine process holds the cache. Close all Auto Dialer windows, end **QtWebEngineProcess** in Task Manager, then restart. |
| `Failed to resolve address for stun.l.google.com` | Temporary network/DNS issue for WebRTC; retry or check internet. |
| `QSystemTrayIcon::setVisible: No Icon set` | Harmless Qt warning; does not affect dialing. |
| `Release of profile requested but WebEnginePage still not deleted` | Fixed in current builds — restart the app fully if it persists. |

## Configuration reference

| Setting | Effect on dialing |
|---------|-------------------|
| `n_slots` | Simultaneous lines |
| `call_timeout` | Seconds before an unanswered call is marked no answer |
| `cooldown` | Base seconds between calls on a slot |
| `dial_stagger_sec` | Offset between starting each slot |
| `voicemail_hangup_sec` | Seconds of voicemail before hanging up |
| `max_retries` | Retries per number |
| `retry_backoff_sec` | Backoff between retries, e.g. `[5, 15, 45]` |
| `watchdog_heartbeat_timeout_sec` | No heartbeat for this long during a call triggers recovery |
| `watchdog_stuck_state_sec` | Stuck in Dialing/Ringing/On call this long triggers recovery |
| `slot_memory_limit_mb` | Total WebEngine memory budget before slots are recycled |
| `slot_recycle_after_calls` | Completed calls on one line before it is recycled |
| `enable_ai_audio` | Fuse local audio capture into call-state detection |
| `audio_device` | Capture device index; blank uses the default output loopback |
| `live_debug_mode` | Print `[CALL DEBUG]` blocks during live polling |

## Related documents

- [DETECTION_PIPELINE.md](DETECTION_PIPELINE.md) — how call state is classified
- [RUNBOOK.md](RUNBOOK.md) — day-to-day troubleshooting
- [LOAD_TEST.md](LOAD_TEST.md) — load testing at scale
- [AMD_TESTING.md](AMD_TESTING.md) — tuning pacing on AMD Ryzen hardware
