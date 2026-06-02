# Indus Transports — Auto Dialer Pro

Professional Windows desktop dialer for Indus Transports LLC. Agents use a simple branded app while Google Voice runs in the background on each line.

## Who uses what

| Role | Who | What they can do |
|------|-----|------------------|
| **Administrator** | You (owner) | First account at install, **Administration** tab, add Google Voice lines, connect accounts, create client users |
| **Agent** | Your clients / dialers | Sign in with credentials you create, load lists, start dialing, listen to lines, view logs and CRM |

**Typical setup (your PC = administrator)**

1. Install the app and create the **administrator** account (once).
2. In **Settings**, add each Google Voice line (email + password) — the app signs in automatically in the background.
3. In **Administration → Export client package…**, create a folder for each client PC (agent login + voice profiles + config).
4. On the **client PC**, install the app, copy the package contents into the app folder, run once — they see **Agent sign-in** only (no admin setup wizard).
5. Give each client **only** their email and password from the export step.

Agents do **not** see Google Voice settings, cannot add voice accounts, and cannot manage users. On a client workstation, even an admin password will not grant administrator features.

## Client PC install (agent-only)

Use this when you configure everything on **your** machine and deliver a ready folder to the client.

### On your PC (administrator)

1. Complete Google Voice setup in **Settings**.
2. **Administration** → **Export client package…**
3. Enter the client’s name, login email, and password (8+ characters).
4. Choose a save location (e.g. Desktop). You get a folder like `IndusTransports_AutoDialer_Client` with:
   - `dialer_config.json` (`deployment_mode: client`)
   - `logs/crm.sqlite3` (single agent account)
   - `data/gv_accounts.json` and `chrome_profiles/` (signed-in voice lines)
   - `CLIENT_SETUP.txt` (instructions and credentials summary)

CLI alternative:

```bash
python scripts/prepare_client_install.py --name "Jane Agent" --email jane@example.com --password "TheirPassword8"
```

### On the client PC

1. Install the same app (Python source or built EXE).
2. Copy **everything** from the export folder into the app directory (merge `logs`, `data`, `chrome_profiles`, replace `dialer_config.json`).
3. Run the app — first screen is **Agent sign-in** only.
4. Client signs in with the email/password you set during export.

If the client sees “Workstation not configured”, the `logs` folder from the package was not copied correctly.

## Features

- Light, client-ready interface
- Hidden Google Voice browser per line (`QWebEngineView`)
- **Automatic sign-in** using saved email/password and persistent profiles
- **Listen** on any line — hear the call through your speakers
- Live status: Waiting, Ringing, On call, Voicemail
- Excel contact import, call timeout, voicemail auto-hangup
- Local CRM and call history
- Windows EXE build script

## Requirements

- Windows 10 or 11
- Python 3.10+ (for development)
- Google Voice account per line
- Microphone/speakers allowed when prompted

```bash
pip install -r requirements.txt
```

## Run

```bash
python autodialer_gui.py
```

## Google Voice lines (administrator)

### Add a line

1. **Settings** → **Add account**
2. Fill in **Display name**, **Google email**, and **Password**
3. Leave **Sign in automatically in background** selected (recommended)
4. The app signs in headless — no window unless Google requires CAPTCHA/2FA
5. If verification is needed: **Settings** → select the line → **Connect account**, finish in the browser, then close

Passwords are stored only in `data/gv_accounts.json` on this PC (not committed to git).

### Duplicate a line (no second login)

**Duplicate** copies the entire browser profile from the source line. If the original was already signed in, the copy is **ready immediately** — no password or login step.

### Connect manually

**Connect account** opens the sign-in window when automatic login fails or Google asks for 2FA.

### Session files

- Profiles: `chrome_profiles/<profile_name>/`
- Ready flag: `chrome_profiles/<profile_name>/.gv_session_ok`

## Dialing workflow (agent or admin)

1. **Dialer** → choose Excel file → **Load contacts** (or **Sample list** for testing)
2. Set **Lines at once**, **Call timeout**, **Voicemail hangup**
3. Confirm each line shows **Ready** on **Live Calls**
4. **Start dialing**
5. On **Live Calls**:
   - **On call** — talk (use **Listen** to hear that line)
   - **Voicemail** — app hangs up and moves on automatically
   - **Next number** / **End call** — manual control

## Listen to a line

On **Live Calls**, click **Listen** on any line. A monitor window opens the Google Voice view for that line so audio plays through your computer. Close the monitor when done; dialing continues in the background.

## How call detection works

The app reads the Google Voice web page (not AI audio). Each ~600ms:

| Status | Meaning |
|--------|---------|
| Ringing | Outbound ring |
| On call | Person answered (timer or hold/mute controls) |
| Voicemail | Greeting / beep detected → auto hangup after configured seconds |
| Waiting | Idle, ready for next number |

## Administration (you only)

- **Add user** — creates **agent** accounts for clients
- **Reset password** / **Activate / deactivate** / **Delete user**
- Admins see all call logs; agents see only their own

## Build EXE

```bash
python build_exe.py
```

Output: `dist/IndusTransports_AutoDialer.exe`

## Data on disk (do not share)

| Path | Purpose |
|------|---------|
| `data/gv_accounts.json` | Voice line emails/passwords |
| `chrome_profiles/` | Google sign-in sessions |
| `logs/crm.sqlite3` | Users, CRM, call history |

## Troubleshooting

### “Google Voice is not ready”

1. **Settings** → **Connect account** for that line  
2. Or wait ~90s after adding an account with automatic sign-in  
3. Check **Live Calls** shows **Ready**

### Blank sign-in window

1. Click **Reload** in the connect dialog  
2. Restart the app (GPU fallback is enabled automatically)  
3. Install: `pip install PyQt6-WebEngine`

### Client cannot change voice settings

Expected — only administrators configure Google Voice. Clients use Dialer and Live Calls only.

## Support

WhatsApp: [+923079670503](https://wa.me/923079670503)
