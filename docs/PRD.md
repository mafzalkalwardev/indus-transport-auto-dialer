# Product Requirements Document (PRD)

## Product: Indus Transport Auto Dialer

**Document owner:** Product / Engineering  
**Repository:** `mafzalkalwardev/indus-transport-auto-dialer`  
**Document status:** Draft v1  
**Created:** 2026-06-24  
**Platform:** Windows desktop application  
**Primary stack:** Python 3.10+, PyQt6, PyQt6 WebEngine, local SQLite/JSON storage, Google Voice web sessions

---

## 1. Executive Summary

Indus Transport Auto Dialer is a Windows desktop calling productivity tool for outbound transport, dispatch, carrier, and sales calling workflows. The application allows an administrator to configure Google Voice lines, create client/agent users, import Excel contact lists, run multi-line dialing campaigns, detect call states, and route the live answered call to the operator while skipping voicemail, busy, no-answer, and failed attempts.

The product must remain simple enough for non-technical agents, while giving the administrator full control over Google Voice accounts, user access, client workstation packages, dialing behavior, logs, and reliability settings.

The current product is positioned as a professional Windows auto dialer using Google Voice, AMD-style answer detection, predictive pacing, CRM/history, Excel lists, embedded Google Voice browser sessions, watchdog recovery, retries, and local-first audio/DOM call-state detection.

---

## 2. Product Vision

Build a reliable, client-ready Windows auto dialer that helps Indus Transport teams and client agents call large contact lists faster, reduce manual dialing work, skip non-human outcomes, and immediately focus the agent on the line where a real person answers.

The long-term vision is to become a lightweight transport/business calling workstation that combines:

- Multi-line outbound dialing
- Human vs voicemail detection
- Local CRM and call history
- Admin-controlled client deployments
- Stable long-campaign execution
- Simple agent UI
- Safe, compliant, auditable calling operations

---

## 3. Problem Statement

Transport and dispatch teams often need to call large lists of carriers, drivers, owner-operators, brokers, or leads. Manual calling is slow because agents spend time dialing, waiting through ringing, hearing voicemail greetings, handling busy signals, and tracking outcomes manually.

The product solves this by allowing the system to dial multiple numbers in parallel, monitor each call, identify the first useful live answer, bring that call to the agent, and log the result locally.

---

## 4. Target Users and Personas

### 4.1 Administrator / Owner

**Who:** Business owner, operations manager, or technical setup person.  
**Goal:** Configure the system once, manage Google Voice lines, create agent users, export client packages, monitor logs, and control dialing settings.

**Needs:**

- Add and manage Google Voice accounts securely.
- Create and manage users.
- Export ready-to-use client workstation packages.
- View all call logs and campaign performance.
- Troubleshoot Google Voice connection, audio detection, and line recovery.
- Keep agents away from backend/provider settings.

### 4.2 Agent / Client Dialer

**Who:** Client user, call center operator, dispatcher, or virtual assistant.  
**Goal:** Sign in, load contacts, start dialing, talk to answered calls, and record outcomes without touching admin settings.

**Needs:**

- Very simple login.
- No Google Voice account setup exposure.
- Load Excel contact lists.
- Start/stop/pause campaigns.
- See live call statuses.
- Immediately talk when a human answers.
- View own CRM/history only.

### 4.3 Support / Technical Operator

**Who:** Internal support person helping install, debug, or package the app.  
**Goal:** Quickly identify setup issues, failed lines, audio problems, stuck slots, or client package mistakes.

**Needs:**

- Clear logs.
- Smoke test scripts.
- Runbook guidance.
- Configurable watchdog/retry settings.
- Easy reproduction of audio/call detection issues.

---

## 5. Goals

### 5.1 Business Goals

1. Reduce time spent on manual outbound dialing.
2. Increase agent talk time with real human answers.
3. Reduce wasted time on voicemail, busy, no-answer, and failed calls.
4. Make the product easy to deploy to client/agent PCs.
5. Support multiple Google Voice lines without exposing provider credentials to agents.
6. Provide logs and CRM history for accountability and follow-up.

### 5.2 Product Goals

1. Provide a clean Windows desktop interface for admin and agent workflows.
2. Enable Excel contact import and campaign execution.
3. Support multi-line dialing with configurable line count and timeouts.
4. Detect call states using browser DOM evidence and local audio signals.
5. Automatically surface a human answered call to the operator.
6. Auto-hangup voicemail when confidence rules are met.
7. Recover stuck lines through watchdog and retries.
8. Store sensitive account data locally and exclude it from Git.
9. Keep the app local-first with no required paid telephony/transcription APIs.

---

## 6. Non-Goals

The following are intentionally out of scope for the current product version:

1. Replacing Google Voice with Twilio, Vonage, or paid carrier APIs.
2. Reverse-engineering private Google Voice APIs or bypassing Google security.
3. Cloud-only call processing as a required dependency.
4. Automatic calling without operator supervision where legally restricted.
5. Built-in legal compliance certification.
6. Call recording unless explicitly required and reviewed for compliance.
7. Screenshot/OCR-based call-state detection as a primary mechanism.
8. Mobile app support.
9. macOS/Linux packaged support for the initial production target.

---

## 7. Current Product Capabilities

The product already includes or documents the following capabilities:

- Windows desktop app built with Python and PyQt6.
- Embedded Google Voice browser per line.
- Admin and agent role separation.
- Google Voice line configuration by administrator.
- Client package export for agent-only workstations.
- Excel contact import.
- Configurable lines-at-once campaign dialing.
- Live status states such as Waiting, Ringing, On call, Voicemail, Busy, No answer, and Ended.
- Local CRM and call history.
- Watchdog recovery for stuck/high-memory lines.
- Retry behavior for failed dials.
- Local-first audio detection using Windows audio capture when available.
- DOM + audio fusion call-state pipeline.
- Smoke test and audio device test scripts.
- Windows EXE build script.

---

## 8. Functional Requirements

### 8.1 Authentication and Roles

#### FR-001: First-Run Admin Setup

The application shall create the first administrator account during initial setup.

**Acceptance Criteria:**

- On first install, user can create admin credentials.
- Admin setup runs only when no admin exists.
- After setup, the app opens normal login flow.

#### FR-002: Agent Login

The application shall allow agents to sign in using credentials created by the administrator.

**Acceptance Criteria:**

- Agent sees only agent-allowed screens.
- Agent cannot access Google Voice account settings.
- Agent cannot manage users.
- Agent cannot switch workstation into admin mode on a client package.

#### FR-003: Role-Based Access Control

The system shall enforce separate permissions for administrator and agent users.

**Acceptance Criteria:**

- Administrator can manage users, lines, packages, settings, and logs.
- Agent can run dialing workflows and view assigned/local data only.
- UI tabs/actions must be hidden or disabled based on role.
- Backend/local logic must also validate permissions, not only hide buttons.

---

### 8.2 Google Voice Line Management

#### FR-010: Add Google Voice Line

Administrator shall be able to add a Google Voice line with display name, email, and password/session profile details.

**Acceptance Criteria:**

- Admin can add line from Settings.
- App creates or reuses a persistent browser profile for the line.
- App stores line configuration locally.
- App can mark line as Ready when sign-in/session is valid.

#### FR-011: Connect Account Manually

Administrator shall be able to open an embedded/browser sign-in flow when automatic sign-in requires verification.

**Acceptance Criteria:**

- Admin can select a line and click Connect account.
- Browser sign-in window opens.
- After successful sign-in, profile/session is persisted.
- Line readiness updates after restart or refresh.

#### FR-012: Duplicate Line Profile

Administrator should be able to duplicate an existing signed-in browser profile for another line where supported by current product behavior.

**Acceptance Criteria:**

- Duplicate action copies profile folder safely.
- Duplicate line is shown in Settings and Live Calls.
- Existing source profile is not corrupted.
- Failure shows a clear message.

#### FR-013: Hide Provider Credentials from Agents

Agents shall never see Google Voice emails, passwords, profile paths, backend configuration, or provider settings.

**Acceptance Criteria:**

- Client package opens agent-only UI.
- Settings tab is not available to agents.
- Sensitive local files are not exposed through UI.

---

### 8.3 Client Package Export

#### FR-020: Export Client Package

Administrator shall be able to export a ready client package for an agent workstation.

**Acceptance Criteria:**

- Admin enters client/agent name, email, and password.
- Export creates a package folder with deployment config, local CRM/user data, Google Voice account data, browser profiles, and setup notes where applicable.
- Client deployment mode is set to agent/client.
- Client package does not expose admin setup wizard.

#### FR-021: CLI Client Package Creation

The product should support CLI-based package generation for repeatable deployments.

**Acceptance Criteria:**

- Script accepts name, email, and password arguments.
- Script creates the same structure as GUI export.
- Script fails safely if required inputs are missing.

---

### 8.4 Contact Import and CRM

#### FR-030: Excel Contact Import

Agent/admin shall be able to import contact lists from Excel.

**Acceptance Criteria:**

- User can choose Excel file.
- App validates required columns or provides mapping guidance.
- Invalid rows are skipped with clear feedback.
- Imported contacts appear in campaign queue.

#### FR-031: Sample List

The app should provide a sample contact list option for testing.

**Acceptance Criteria:**

- User can load sample data without external files.
- Sample data is clearly labeled as test/demo.

#### FR-032: Local CRM History

The app shall store call outcomes locally.

**Acceptance Criteria:**

- Each call attempt stores phone number, status, timestamp, line, final outcome, detection reason, confidence, and optional notes where available.
- Admin can view all logs.
- Agent can view only allowed/local call logs.
- Logs survive app restart.

#### FR-033: Export Call Logs

The app should allow exporting call logs to CSV.

**Acceptance Criteria:**

- Export includes final outcome and detection reason.
- Export can be filtered by date/campaign/agent where available.
- Export handles empty logs gracefully.

---

### 8.5 Dialing Campaigns

#### FR-040: Campaign Setup

User shall be able to configure campaign settings before dialing.

**Acceptance Criteria:**

- User can choose contact list.
- User can set lines at once.
- User can set call timeout.
- User can set voicemail hangup behavior.
- App validates selected line count against ready Google Voice lines.

#### FR-041: Start / Pause / Stop Campaign

User shall be able to control campaign execution.

**Acceptance Criteria:**

- Start begins dialing available lines.
- Pause prevents new calls while allowing current live call handling.
- Stop ends active dialing safely.
- UI always reflects current campaign state.

#### FR-042: Multi-Line Dialing

The app shall dial multiple contacts in parallel up to the configured line count.

**Acceptance Criteria:**

- Each active line has independent status.
- Dialer does not exceed configured simultaneous lines.
- Dialer does not call the same contact twice within the same campaign unless retry rules require it.
- Ready lines are reused after call outcome is finalized.

#### FR-043: Answered Call Focus

When a human answer is detected, the app shall highlight and open the corresponding live line panel for the operator.

**Acceptance Criteria:**

- Human answer changes line status to On call or equivalent.
- The answered line is visually highlighted.
- Embedded Google Voice panel opens or focuses for the operator.
- Other lines can continue, pause, or be controlled according to pacing rules.

#### FR-044: Manual Controls

User shall be able to manually end, release, or move to next number.

**Acceptance Criteria:**

- End call hangs up active line.
- Release slot/next moves line to next queued contact.
- Manual action is logged.
- UI does not freeze during manual action.

---

### 8.6 Call-State Detection

#### FR-050: DOM-Based Detection

The app shall detect basic Google Voice call states using visible/embedded web UI state.

**Acceptance Criteria:**

- Detects dialing/ringing.
- Detects answer evidence from call controls/timer where available.
- Detects ended/failed browser states where available.
- DOM-only detection continues when audio backend is unavailable.

#### FR-051: Local Audio Detection

The app should use local Windows audio capture to improve answer, voicemail, busy, and silence detection.

**Acceptance Criteria:**

- Audio capture tries WASAPI loopback first where available.
- App can fall back to other capture devices such as Stereo Mix/VB-Cable where available.
- App reports AI Audio ON, OFF, or NO BACKEND.
- Detection continues without crashing when no audio backend is available.

#### FR-052: Human Pickup Detection

The app shall identify likely human pickup using short speech/noise/timing signals.

**Acceptance Criteria:**

- Short greeting patterns are treated as human or answered-pending.
- Early background noise alone does not automatically become voicemail.
- Human answer can override voicemail suspicion when confidence is higher.

#### FR-053: Voicemail Detection

The app shall classify voicemail conservatively to avoid hanging up on humans.

**Acceptance Criteria:**

- Ringing never becomes voicemail directly.
- Voicemail classification requires answer evidence.
- Voicemail requires elapsed time, confidence, and multiple strong signals.
- App auto-hangups voicemail only when configured and confidence threshold is met.

#### FR-054: Busy and No-Answer Detection

The app shall classify busy and no-answer outcomes.

**Acceptance Criteria:**

- Busy tone/cadence is detected where audio evidence supports it.
- No-answer is assigned only after configured timeout.
- Final outcome is logged with reason.

#### FR-055: Detection Debug Output

The app should provide debug output for testing and support.

**Acceptance Criteria:**

- Debug blocks include DOM state, audio state, fused state, confidence, reason, and should_hangup.
- JSON test reports are written under logs when smoke tests run.

---

### 8.7 Reliability and Recovery

#### FR-060: Watchdog Recovery

The app shall recover stuck lines automatically.

**Acceptance Criteria:**

- Watchdog detects missing heartbeat.
- Watchdog detects stuck Dialing/Ringing/On call state after configured timeout.
- Watchdog can recycle high-memory or overused WebEngine line profiles.
- Recovery event is logged.

#### FR-061: Retry Failed Dials

The app shall retry failed calls according to configurable retry policy.

**Acceptance Criteria:**

- Failed call retries up to max retry count.
- Backoff schedule is configurable.
- After max retries, status becomes FAILED.
- Retry history is visible in logs.

#### FR-062: Long Campaign Stability

The app should support long campaigns with many contacts and multiple slots.

**Acceptance Criteria:**

- HTTP cache clears when starting/stopping campaigns where applicable.
- Slot recycling prevents memory growth.
- Load test scripts can generate large lists.
- App remains responsive during 1000+ number test campaigns on supported hardware.

---

### 8.8 Build and Packaging

#### FR-070: Windows EXE Build

The product shall provide a repeatable Windows EXE build process.

**Acceptance Criteria:**

- Build script produces executable under `dist/`.
- Build output includes required resources/config defaults.
- Sensitive local runtime data is not bundled accidentally.
- README/runbook explain build command.

#### FR-071: Development Run Mode

Developers shall be able to run the app from source.

**Acceptance Criteria:**

- `pip install -r requirements.txt` installs required packages.
- `python autodialer_gui.py` starts the app.
- Missing optional audio backends degrade gracefully.

---

## 9. Non-Functional Requirements

### 9.1 Usability

- Agent UI must be simple, clean, and low-confusion.
- Admin-only features must be clearly separated.
- Live Calls screen must make the active human call obvious.
- Error messages should tell the user what to do next.

### 9.2 Performance

- App should remain responsive while dialing multiple lines.
- UI updates should not block call-state polling.
- Detection loop should be lightweight enough for Windows laptops/desktops.
- Memory must be monitored and recycled during long campaigns.

### 9.3 Reliability

- A single bad line must not crash the whole campaign.
- Network/Google Voice issues should produce clear recoverable states.
- Logs must capture enough context for support.
- Watchdog recovery should avoid duplicate uncontrolled calls.

### 9.4 Security

- Google Voice credentials and session data must remain local.
- Sensitive files such as `data/gv_accounts.json`, `chrome_profiles/`, and `logs/crm.sqlite3` must not be committed to Git.
- Agent UI must not expose provider credentials or admin controls.
- Passwords should be protected at rest where feasible for the Windows deployment model.
- Client package export must be handled carefully because it may include signed-in profiles.

### 9.5 Privacy and Compliance

- The product must support responsible calling practices.
- Users are responsible for ensuring consent, lawful calling hours, internal DNC lists, and any applicable telemarketing/communications rules.
- Product documentation should include compliance warnings before enabling high-volume campaigns.
- Call recording should remain disabled unless legal review and consent flows are implemented.

### 9.6 Maintainability

- Detection logic should remain modular: DOM stage, audio stage, VAD stage, human/voicemail scoring, and final state machine.
- Configurable thresholds should live in config files, not hardcoded scattered values.
- Scripts should exist for smoke tests, audio device checks, and load test generation.
- Logs should be structured enough to debug false positive/false negative detection cases.

---

## 10. User Experience Requirements

### 10.1 Administrator Flow

1. Install/run app.
2. Create administrator account.
3. Add Google Voice lines.
4. Connect accounts and confirm Ready status.
5. Create agent/client users.
6. Export client packages as needed.
7. Monitor logs and support agents.

### 10.2 Agent Flow

1. Open app on configured client PC.
2. Sign in with provided credentials.
3. Load Excel contact list.
4. Select campaign settings.
5. Confirm lines are ready.
6. Start dialing.
7. Talk when human answer appears.
8. End/release call and continue campaign.
9. Review own call history.

### 10.3 Support Flow

1. Check deployment mode: admin or client.
2. Check Google Voice readiness.
3. Run audio device test.
4. Enable live debug mode.
5. Run live smoke test.
6. Review latest `logs/dialer.log` and JSON report.
7. Adjust config if needed.

---

## 11. Data Requirements

### 11.1 Runtime Data

| Data | Storage | Notes |
|------|---------|-------|
| Google Voice line credentials | `data/gv_accounts.json` | Local only, sensitive |
| Browser sessions | `chrome_profiles/` | Local only, sensitive |
| CRM/users/call history | `logs/crm.sqlite3` | Local database |
| Call/debug logs | `logs/dialer.log`, JSON reports | Used for troubleshooting |
| Config | `dialer_config.json` | Runtime settings |
| Detection samples | `data/detection_samples/` | Ignored local dataset |

### 11.2 Call Log Fields

Recommended minimum fields:

- Call ID
- Campaign ID
- Agent/user ID
- Phone number
- Contact name
- Line/profile used
- Start timestamp
- End timestamp
- Duration
- Final status
- Detection confidence
- Detection reason
- Retry count
- Manual/automatic outcome flag
- Notes/disposition

---

## 12. Detection Pipeline Requirements

The product should follow a staged detector design:

1. Dial call.
2. Detect ringing/dialing through DOM and ringback evidence.
3. Detect answer evidence through DOM controls/timer and audio changes.
4. Run VAD on captured audio.
5. Score human vs voicemail based on timing, speech, transcript keywords, beep, silence, and cadence.
6. Emit final finite-state-machine decision.
7. Log state history and confidence.

### Required States

| State | Meaning |
|------|---------|
| Waiting | Line is idle and ready |
| Dialing | Number is being dialed |
| Ringing | Outbound call is ringing |
| Checking answer | Answer evidence exists, waiting for classification |
| On call / Human | Human pickup detected |
| Voicemail | Voicemail detected with confidence |
| Busy | Busy tone/cadence detected |
| No answer | Timeout reached without answer |
| Failed | Browser, network, or dialing failure |
| Ended by operator | Manual hangup/release |
| Recovering | Watchdog is recycling line |

---

## 13. Configuration Requirements

The following configuration values should remain adjustable:

- `max_retries`
- `retry_backoff_sec`
- `watchdog_heartbeat_timeout_sec`
- `watchdog_stuck_state_sec`
- `slot_memory_limit_mb`
- `slot_recycle_after_calls`
- `watchdog_check_interval_sec`
- `enable_ai_audio`
- `audio_device`
- `live_debug_mode`
- `call_timeout`
- `voicemail_hangup_seconds`
- `n_slots` / lines at once

Config changes should be validated before use and should not require code changes.

---

## 14. Success Metrics

### 14.1 Product Metrics

- Percentage of calls correctly classified by final outcome.
- False voicemail rate where human calls were incorrectly hung up.
- Average agent wait time before human pickup.
- Calls completed per hour.
- Average talk time per active campaign.
- Failed/stuck line recovery count.
- Campaign completion rate.

### 14.2 Reliability Metrics

- App crash rate during campaigns.
- Watchdog recovery success rate.
- Memory usage after 100, 500, and 1000 calls.
- Number of calls before slot recycle.
- Audio backend availability rate.

### 14.3 Business Metrics

- Agent productivity improvement vs manual dialing.
- Number of client PCs successfully deployed.
- Support tickets per installation.
- Time required to configure a new client package.

---

## 15. Acceptance Test Plan

### 15.1 Admin Setup Test

- Fresh install opens admin setup.
- Admin can create account.
- Admin can add Google Voice line.
- Line reaches Ready state after sign-in.

### 15.2 Client Package Test

- Admin exports package.
- Package copied to clean client folder.
- Client app opens agent sign-in only.
- Agent cannot access admin screens.

### 15.3 Campaign Smoke Test

- Load sample contacts.
- Configure one line.
- Start campaign.
- Verify states move through Waiting/Dialing/Ringing/final outcome.
- Verify logs are written.

### 15.4 Multi-Line Test

- Configure at least two ready lines.
- Load test list.
- Start campaign with two slots.
- Verify independent statuses and no duplicate uncontrolled calls.

### 15.5 Detection Test

- Run `scripts/audio_device_test.py`.
- Run `scripts/live_call_smoke.py`.
- Verify debug output includes DOM/audio/fused state.
- Confirm voicemail is not triggered directly from ringing.

### 15.6 Long Campaign Test

- Generate load test list.
- Run with supported number of slots.
- Monitor memory and watchdog logs.
- Confirm app remains responsive.
- Confirm final report/logs are complete.

---

## 16. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Google Voice UI changes | Detection/sign-in may break | Keep DOM detection modular, add smoke tests, document manual connect fallback |
| Google account 2FA/CAPTCHA | Automatic sign-in may fail | Provide Connect account flow and persistent profiles |
| Audio backend unavailable | Weaker detection | Continue with DOM-only detection and show AI Audio status |
| False voicemail detection | Human calls may be dropped | Conservative voicemail rules, require answer evidence and multiple signals |
| High memory usage from WebEngine | Long campaigns become unstable | Watchdog, slot recycle, cache clearing, load tests |
| Sensitive client package data | Credential/session exposure | Admin warnings, local-only storage, never commit runtime folders |
| Legal/compliance misuse | Business/legal risk | Compliance warnings, opt-out/DNC support roadmap, no recording by default |

---

## 17. Roadmap

### Phase 1: Stabilized Current Release

- Confirm admin/agent role boundaries.
- Improve logs and error messages.
- Validate client package export/install path.
- Ensure `.gitignore` protects runtime sensitive folders.
- Improve runbook coverage for common setup problems.

### Phase 2: Detection Quality Upgrade

- Expand local detection samples.
- Add better offline evaluation reports.
- Track false human/false voicemail decisions.
- Add configurable confidence thresholds.
- Improve busy/no-answer classification.

### Phase 3: CRM and Campaign Management

- Add campaign names and saved campaign history.
- Add dispositions/notes after calls.
- Add contact status filters.
- Add CSV/Excel export improvements.
- Add duplicate contact prevention across campaigns.

### Phase 4: Compliance and Admin Controls

- Add internal Do Not Call list.
- Add per-campaign consent/compliance checklist.
- Add calling-hours guardrails by timezone where needed.
- Add audit logs for package export and admin changes.

### Phase 5: Packaging and Client Delivery

- Improve installer/EXE packaging.
- Add guided setup wizard for admin PC.
- Add package integrity check for client PC.
- Add update instructions for existing client deployments.

---

## 18. Open Questions

1. Should the customer-facing brand remain Indus Transport Auto Dialer, FT Solutions Auto Dialer, or support both as deployment branding?
2. Should agent CRM data sync back to admin, or remain fully local per workstation?
3. What is the maximum supported number of simultaneous lines on target client hardware?
4. Should the app include a required compliance checklist before campaign start?
5. Should call recording ever be added, or remain out of scope permanently?
6. Should paid transcription/provider integrations remain optional future plugins only?
7. Should packages expire or require license/activation for client PCs?

---

## 19. Definition of Done

A release is considered done when:

- Admin can configure lines and users.
- Agent can run dialing without seeing admin settings.
- Excel import and sample list both work.
- Multi-line campaign execution is stable.
- Human answer, voicemail, busy, no-answer, and failed outcomes are logged.
- Watchdog/retry behavior works during stuck/failure cases.
- Client package export works on a clean client workstation.
- Runbook and README match the shipped behavior.
- Sensitive runtime files are not tracked in Git.
- Smoke tests and audio device tests pass on the target Windows environment.

---

## 20. Appendix: Recommended Documentation Links

- `README.md` — setup, features, run, build, troubleshooting.
- `docs/RUNBOOK.md` — operations and support guide.
- `docs/DETECTION_PIPELINE.md` — call-state detection design.
- `docs/LOAD_TEST.md` — long campaign and load testing.
- `scripts/audio_device_test.py` — local audio backend verification.
- `scripts/live_call_smoke.py` — live call detection smoke testing.
- `scripts/prepare_client_install.py` — client package creation.
