# Working State Plan

This file is the implementation plan and current operating contract for the
Google Voice auto dialer. It exists so fixes are made against the confirmed
workflow instead of guessing from one log line at a time.

## Current Failure Seen

The monitor screenshot shows Google Voice displaying an active call panel while
the app status banner says:

`Dialpad did not appear - reloading Google Voice calls...`

That means the recovery path is trying to reload `/calls` after a call panel is
already open. Google Voice then raises a JavaScript confirm dialog:

`Are you sure you want to leave this page? Changes that you made may not be saved.`

The correct behavior is: once an active call panel/hangup button is visible, the
dialer must stop dialpad recovery and switch to call-state polling. It must not
reload the page over a live call.

## Plan

1. Add a browser-page guard for Google Voice JavaScript confirm dialogs so an
   accidental navigation prompt cannot block the monitor.
2. Add an active-call DOM probe that detects hangup/call controls or active call
   panel text.
3. Before retrying or reloading after `number_input_missing`,
   `call_button_wrong_number`, or `call_button_missing`, check the active-call
   probe.
4. If a call panel is active, mark the dial click as accepted, clear the pending
   dial number, start polling, and do not reload.
5. Keep stale/wrong-number protection: never click a call button whose label
   contains a different phone number.
6. Preserve VICIdial-style classification:
   `IDLE -> DIALING -> RINGING -> ANSWERED_PENDING -> CONNECTED/HUMAN or VOICEMAIL/BUSY/NO_ANSWER/FAILED -> LOG_RESULT -> NEXT_LEAD`.
7. Update README with the real state machine, recovery behavior, dry-run/smoke
   testing rules, and the JavaScript confirm screenshot explanation.
8. Verify with syntax checks and unit tests. Live calling must use only
   owner-approved CRM/test numbers.

## State Contract

- `RINGING` is not `VOICEMAIL`.
- `RINGING` is not `FAILED`.
- `RINGING` is not `ENDED`.
- No hangup during ringing before timeout.
- Voicemail classification requires answer evidence first.
- The UI should show/treat a talkable call only after human/live answer
  evidence, not while the call is merely ringing.
- Unknown connected audio remains in `ANSWERED_PENDING` briefly before final
  classification.
- Each call should log one final status.

## Verification

Automated verification should include:

- `_js_dial(...)` JavaScript syntax check.
- Unit tests for stale call-button rejection.
- Unit tests for VICIdial-style ringing/voicemail gating.
- Full `pytest` suite.

Live verification should be run only with approved test/CRM contacts:

```bash
python scripts/live_call_smoke.py --from-crm --crm-limit 2 --call-timeout 45
```

