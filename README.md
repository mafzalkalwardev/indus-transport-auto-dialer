# INDUS TRANSPORTS LLC - Auto Dialer Pro

Windows desktop auto dialer for Indus Transports LLC using Google Voice in hidden embedded browser profiles. Agents work from the branded app UI while Google Voice stays in the background.

## Features

- Branded PyQt6 desktop UI with admin login, agent login, CRM, logs, and live call panels
- Hidden Google Voice browser per call slot using `QWebEngineView`
- Google Voice account manager with persistent profile folders
- Automatic Google Voice login using saved local email/password plus persistent browser sessions
- Live call cards showing slot status, current phone number, and call duration
- Operator controls for `Next Call` and `Cut Call`
- Call timeout auto-cut for unanswered dialing/ringing calls
- Excel import with phone validation and resume support
- Local SQLite CRM and call history
- PyInstaller build script for a Windows EXE

## Screenshots

These interface previews show the current live-call console and the refreshed light-mode settings screen.

![Live Calls dark mode](docs/screenshots/live-calls-dark.png)

![Settings light mode](docs/screenshots/settings-light.png)

## Requirements

- Windows 10 or 110
- Python 3.10+
- Google Voice account(s)
- Microphone permission allowed when the Google Voice setup window asks

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run

```bash
python autodialer_gui.py
```

On first run, create the admin account. Admin users can create app users from the Admin tab.

## Google Voice Account Setup

1. Open `Settings`.
2. In `Google Voice Accounts`, click `+ Add Account`.
3. Enter a label and the Google Voice email.
4. Enter the Google Voice password when prompted.
5. Choose `Login / Setup Selected` — an **embedded browser** opens inside the app (not a separate Chrome window).
6. Sign in on the live Google page. Saved email/password autofill when possible.
7. If Google asks for CAPTCHA, 2FA, recovery email, or another security challenge, complete it in that same window.
8. The setup window closes automatically when login is detected, or click **I'm Logged In — Continue**.

Each account gets its own persistent profile under `chrome_profiles/`. On future launches, the app reopens that same profile so Google Voice is already signed in. Passwords are stored only in the local ignored file `data/gv_accounts.json`; do not commit or share that file. The app does not bypass Google CAPTCHA, 2FA, or security checks.

Slots use accounts in order:

- Slot 1 uses the first Google Voice account.
- Slot 2 uses the second Google Voice account.
- Extra slots fall back to legacy `slot_N` profile folders if there are fewer accounts than slots.

Use `Move Up`, `Move Down`, and `Duplicate` in Settings to control account priority. Duplicated accounts get separate profile folders, which is useful for testing profile priority without retyping credentials.

## Dialing Workflow

1. In the Dialer tab, select an Excel file.
2. Click `Load Numbers`.
3. Set simultaneous slots, call timeout, and cooldown.
4. Click `Start Power Dial`.
5. Watch active calls from the Live Calls tab.

Live call controls:

- `Next Call`: cuts the current backend Google Voice call and immediately advances the slot.
- `Cut Call`: hangs up the current backend Google Voice call and leaves the slot idle until the dialer assigns another call.
- Timeout: unanswered `DIALING` or `RINGING` calls are cut automatically after the configured timeout.

## How Call Detection Works (Headless)

The app does **not** use AI or audio analysis. Each hidden `QWebEngineView` reads the Google Voice web UI every ~600ms and classifies the call using DOM signals:

| State | How it is detected |
|-------|-------------------|
| **RINGING** | Hangup visible, “Ringing” / “Calling” text |
| **CONNECTED** | Live call timer (`MM:SS`) or Hold/Mute/Transfer buttons (2 polls) |
| **VOICEMAIL** | Phrases like “leave a message”, “after the beep”, or voicemail UI (2 polls) |
| **ENDED** | “Call ended” banner |

Voicemail is checked **before** ringing/connected so a VM greeting is not mistaken for a live answer. After voicemail is confirmed, the app hangs up automatically (see **Voicemail hangup** on the Dialer tab) and dials the next number. Live answers switch to the **Live Calls** tab without blocking popups.

## Live Test Notes

Use only phone numbers you own or are explicitly authorized to call. The app can log in automatically with saved local credentials, but Google security checks such as CAPTCHA, 2FA, or recovery prompts must be completed manually.

## Troubleshooting

### Empty login window (dark panel, no Google page)

This was caused by the hidden dialer browser staying at 1×1 pixels during setup. Current builds expand the embedded view for **Login / Setup Selected**. If the page is still blank:

1. Click **Reload page** in the setup dialog.
2. Confirm `PyQt6-WebEngine` is installed: `pip install PyQt6-WebEngine`.
3. On some GPUs, try launching with software rendering before starting the app:

```bat
set QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu
python autodialer_gui.py
```

### Power Dial disabled

Ensure each active slot's Google Voice account shows **READY** on the Live Calls tab, or run **Login / Setup Selected** again in Settings.

## Excel File Format

The spreadsheet must include a phone column named one of:

```text
Phone | Mobile | Number | Tel | Telephone | Cell | Phone Number
```

Optional name columns:

```text
Name | Full Name | Contact Name
```

Supported phone formats include `3055551234`, `+13055551234`, `(305) 555-1234`, `305-555-1234`, and `305.555.1234`.

## Build EXE

```bash
python build_exe.py
```

Output:

```text
dist/IndusTransports_AutoDialer.exe
```

## Runtime Data

Runtime folders are intentionally not committed:

- `Archive_OldProjects/`
- `chrome_profiles/`
- `logs/`
- `data/gv_accounts.json`
- `build/`
- `dist/`

## Safety Note

This app only automates authorized Google Voice sessions after a user logs in manually. It does not access Google APIs, store Google passwords, or bypass Google security checks.

## Support

WhatsApp: [+923079670503](https://wa.me/923079670503)
