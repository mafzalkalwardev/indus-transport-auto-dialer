# Deep workflow analysis (current app)

This document reconstructs the *actual runtime workflow* from the current code, then highlights where the workflow is fragile / “messed up”, what appears wrong, and what should be improved.

> Scope: `autodialer_gui.py` (UI + campaign scheduler), `src/gv_controller.py` (per-slot embedded browser + call detection + login automation), `src/call_state_engine.py` (browser evidence → state), `src/retry_queue.py` (retries), `src/slot_watchdog.py` (stuck slot recovery).  

---

## 1) System components and their responsibilities

### A. UI & campaign controller (`autodialer_gui.py`)
MainWindow owns the campaign loop:
- Holds `self._controllers: list[GVController]` (one controller per line/slot).
- Holds dial queue state:
  - `self._contacts: list[(phone,name)]` and `_contact_idx`
  - per-slot state caches: `_slot_phone`, `_slot_start`, `_slot_name`, `_slot_retry_attempt`, `_slot_cooldown_until`.
- Runs timers:
  - `_dial_timer` + `_assign_debounce` to assign the next number into free slots.
  - `_elapsed_timer` to refresh slot elapsed time on UI cards.
  - `_headless_timer` to attempt background GV sign-in for configured accounts.
- Handles user actions:
  - Start/Stop dialing.
  - Cut/Release slot.
  - Listen/Monitor (temporary reparenting of the slot’s `QWebEngineView`).

### B. Per-slot controller (`src/gv_controller.py`)
Each GVController is one embedded WebEngine session / Chrome profile:
- Owns:
  - `self._page` / `self._profile` and `self.view`.
  - login automation (autofill) and sign-in detection.
  - polling timer (`_poll_timer`) that calls `_poll_state()`.
- Provides API used by UI:
  - `load(for_setup=...)` (load GV page or sign-in page)
  - `set_login_credentials(email,pw)`
  - `dial(phone)` (runs JS dial sequence; starts polling)
  - `hangup()` (runs JS hangup; stops polling)
  - `current_state` property
  - `state_changed` signal
  - `log_message` signal
  - `heartbeat` signal
  - `mark_logged_in()` / `is_session_ready()`

### C. Evidence → state (`src/call_state_engine.py`)
The state engine is conservative:
- Uses browser-provided evidence (structured dict from JS in `gv_controller`).
- Maps it into states:
  - `VOICEMAIL`
  - `RINGING`
  - `CONNECTED` (only if timer evidence is present)
  - Otherwise passes through explicit browser states when recognized.

### D. Retry queue (`src/retry_queue.py`)
Holds retry entries with exponential backoff. UI consumes ready entries using `pop_ready()`.

### E. Watchdog (`src/slot_watchdog.py`)
Detects stuck slots:
- Uses heartbeat and last state-change timestamps.
- Also uses a (heuristic) memory metric (sums RSS of qtwebengine/chrome processes via psutil).
- When stuck conditions are met, emits `slot_restart_requested(slot_id, reason)`.
UI handles restart by disposing the controller and re-creating it.

---

## 2) The current runtime workflow (end-to-end)

### Phase 0 — Startup routing
`DialerApp._route_startup()`:
- If client deployment:
  - If no users found in `CRMDatabase`, show “Client not configured”.
  - Else show login page.
- If admin deployment:
  - If db needs admin setup, show admin setup.
  - Else show login.

### Phase 1 — MainWindow boot
`MainWindow.__init__()` does:
1. Builds hidden 1×1 browser host widget.
2. Builds header + tabs.
3. Creates dial/campaign state structures.
4. Calls `_init_controllers(cfg.get('n_slots',5))`:
   - Clears old controllers, unregisters from watchdog.
   - For each slot i:
     - If there is a configured GV account in `_gv_accounts`, uses that account’s `profile_dir` and credentials.
     - Else creates a placeholder profile for `slot_i`.
     - Creates GVController and connects signals.
     - Parents its `QWebEngineView` into the hidden browser host.
     - Starts `ctrl.load()` and schedules `_check_login` if session marker is missing.
5. Starts watchdog.

### Phase 2 — Background login attempts (admin “Settings”)
UI has headless sign-in queue:
- `_start_headless_login(acct)`:
  - ensures a controller exists for the profile
  - sets credentials
  - if session not ready: calls `ctrl.load()` and appends a job into `_headless_login_queue`
- `_tick_headless_logins()` every 2s:
  - checks for session marker / ctrl readiness
  - if not ready, calls `ctrl._check_login()` and sometimes `ctrl._try_auto_login()`.

### Phase 3 — Start dialing (campaign scheduler)
User clicks Start:
1. `_start_dialing()`:
   - Ensures `_contacts` exists or loads from CRM.
   - Checks `_dialing_login_ok()`:
     - requires that each selected slot has a ready GV session (by account ordering and profile readiness).
   - Writes config fields from UI into `self.cfg` and saves to `dialer_config.json`.
   - Re-init controllers and rebuilds slot cards if slot count changed.
2. Sets `self._running=True`.
3. Initializes slot cooldown offsets:
   - `_slot_cooldown_until[i]=_now()+ i*stagger`.
4. Calls `_configure_watchdog()`.
5. Starts timers:
   - `_dial_timer` at interval based on cooldown
   - `_elapsed_timer` every 1s
6. Schedules first assignment via `_schedule_assign()`.

### Phase 4 — Assigning numbers to slots
`_assign_pending_calls()` is the heart of scheduling:
- It does two things:
  1. Tries to pop a ready retry entry (but implementation is *odd*; see Issues).
  2. Loops over all controllers and, for each one that passes `_controller_available(ctrl)`, dials next contact from `_contacts`.

**Availability constraints** (`_controller_available`):
- Slot has an account.
- No active phone assigned.
- `ctrl.current_state` must be in (`IDLE`, `ENDED`, `FAILED`) (i.e. not ringing/connected).
- Cooldown satisfied.

When a slot is selected:
- `_dial_on_slot(ctrl, phone, name, retry_attempt)`:
  - updates UI caches for that slot
  - updates the slot card to `DIALING`
  - calls `ctrl.dial(phone)`
  - schedules a local timeout timer using `_timeout_call()`.

### Phase 5 — Call execution inside GVController
Inside `GVController.dial(phone)`:
1. `_set_state('DIALING')`
2. JS dial sequence `_js_dial(phone)` is executed.
3. Controller attempts to ensure the GV calls page is open.
4. After click/dial attempts, it starts polling state via `_poll_timer`.
5. Polling calls:
   - `_JS_DETECT_STATE` (huge JS snippet)
   - passes the returned evidence dict into `CallStateEngine.classify()`
   - maps it into operator state strings

Important: CONNECTED is strict.
- `CallStateEngine` requires timer evidence to promote to CONNECTED.
- If ringing text exists and no timer is present → remains RINGING.

### Phase 6 — UI receives state changes
`GVController.state_changed(slot_id, state)` → `MainWindow._on_slot_state()`:
- updates card, logs messages.
- For states:
  - `CONNECTED`: focuses that slot’s card and switches UI tab to Live Calls.
  - `VOICEMAIL`: logs to DB as VOICEMAIL immediately, schedules hangup→next.
  - `ENDED`: logs ENDED, then `_finish_slot_call(slot_id)` (cooldown & next assignment)
  - `NO_ANSWER`: logs NO_ANSWER, then `_finish_slot_call(slot_id)`
  - `FAILED`: invokes retry handling / log FAILED.

### Phase 7 — Human agent takeover (CONNECTED)
When `CONNECTED` is detected, UI enables:
- “Listen” (opens SlotMonitorDialog)
- “Release slot / next” and “End call”

SlotMonitorDialog embeds the same `QWebEngineView`:
- It removes the view from hidden host and reparents it into the dialog layout.
- Forces repaint + `_JS_FORCE_VISIBLE` calls.
- Sets `ctrl.set_audio_muted(False)`.

When user clicks release/end:
- “Release slot / next” calls `MainWindow._next_call()` → `_cut_call()` with advance logic.
- `_cut_call()` calls `ctrl.hangup()` and logs ENDED/NO_ANSWER depending on previous state.

### Phase 8 — Watchdog restart
If watchdog decides a slot is stuck:
- UI runs `_restart_slot(slot_id, reason)`:
  - marks recovering on UI
  - calls `ctrl.hangup()`, `ctrl.stop_polling()`, and `_dispose_controller(ctrl)`
  - recreates a fresh GVController for that slot’s profile_dir
  - registers it with watchdog
  - resets UI caches
  - queues retry depending on whether call had a phone.

---

## 3) What is “messed up” / fragile in the current workflow

Below are the main workflow problems observed by reading the code paths.

### Issue 1 — Retry scheduling has been improved; keep regression coverage
Current `_assign_pending_calls()` now drains all ready retries before assigning
fresh contacts, respects the predictive pacing `max_assign` limit, and requeues
deferred retry entries without incrementing their attempt count.

The remaining risk is regression: retry fairness depends on the UI scheduler,
`DialRetryQueue.defer()`, `DialRetryQueue.pop_ready()`, and
`DialRetryQueue.requeue()` staying aligned. Keep focused tests around:
- preserving attempt count when a ready retry is requeued because no line is
  available
- ensuring retries are assigned before new contacts when lines are idle
- ensuring predictive pacing caps apply to retries and fresh contacts together

### Issue 2 — UI cooldown vs watchdog cooldown/restart can fight
There are multiple timers/cooldowns:
- `_slot_cooldown_until` set when starting/stopping.
- `_schedule_assign()` debounces assignment.
- `_restart_slot()` imposes `now - _slot_restart_cooldown[slot_id] < 60` guard.
- GVController has its own dial-stuck timer (35 seconds) that can mark FAILED.

**Workflow conflict:** a slot can be marked FAILED by GVController dial-stuck timer, while watchdog later restarts it; meanwhile UI already started cooldown & rescheduling. This can create:
- duplicated retries
- inconsistent state transitions in DB logs
- “Recovering line” UI that still had queued timeout timers running.

### Issue 3 — SlotMonitor audio/visibility plumbing is complex and easy to desync
Listen window does:
- reparent view from hidden host into dialog layout
- `ctrl.prepare_for_visible_display()` does multiple repaint and JS calls
- `controller.set_audio_muted(False)`

But there is also global hidden container of 1×1 views.

**Risk points:*/
- When watchdog restarts a slot, it disposes the controller, but an already-open SlotMonitorDialog may still hold references to the old controller view.
- `_open_slot_monitor()` stores dialogs in `_slot_monitors`. When dialogs close, `finished` pops by slot_id. But if the slot controller was replaced, the existing dialog might still show the old page.

This is a workflow fragility: operator sees “blank” monitor or audio not working after recovery.

### Issue 4 — Connected detection relies on brittle DOM/timer selectors
`gv_controller.py` promotes to CONNECTED only if JS finds timer evidence matching a strict regex.
- Timer selector list includes:
  - `'[jsname="pRLmDf"]'`
  - `'.call-duration'`
  - `'[aria-label*="call duration" i]'`
  - `'[data-e2eid="call-timer"]'`

But if Google Voice UI changes:
- `CONNECTED` may never happen → dialing stays RINGING until timeout → everything becomes NO_ANSWER/FAILED.
- Conversely, false positives might promote too early if timer appears while still ringing.

This is the single point of failure for the whole workflow.

### Issue 5 — DB logging for VOICEMAIL happens before voicemail hangup certainty
In `MainWindow._on_slot_state()`:
- On `state == "VOICEMAIL"`:
  - logs VOICEMAIL to DB
  - records call completed
  - schedules hangup+next after `vm_sec`

But GVController also auto-hangups voicemail when it detects VOICEMAIL in its JS poll loop: it calls `stop_polling()` after set_state('VOICEMAIL'). Then UI hangup happens later.

**Risk:** if VOICEMAIL is misclassified briefly while ringing, DB will record a voicemail outcome even if the agent later cuts the call or if it transitions to CONNECTED.

### Issue 6 — State strings diverge between layers
There are multiple parallel state representations:
- UI uses strings: `
