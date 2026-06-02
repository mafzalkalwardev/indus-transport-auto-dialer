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

## Requirements

- Windows 10 or 11
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
5. Choose `Login / Setup Selected`.
6. The app will autofill Google's normal email/password pages through the DOM.
7. If Google asks for CAPTCHA, 2FA, recovery email, or another security challenge, finish that step manually in the setup window.
8. Close/continue after login is complete.

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
