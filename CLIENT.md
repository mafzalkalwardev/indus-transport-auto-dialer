# Client Install Guide

This guide is for the **client PC** — the machine that an agent uses to dial. It assumes an
administrator has already configured Google Voice lines and exported a client package.

If you received a folder named `FTSolutions_AutoDialer_Client` from your administrator,
start at [Install from an exported package](#install-from-an-exported-package).

## Requirements

- Windows 10 or 11
- Python 3.10 or newer (only if you run from source; the built EXE has no requirement)
- A microphone and speakers that Windows can use for Google Voice calls
- The client email and password supplied by your administrator

## Install from an exported package

Your administrator sends you a folder that contains:

| Item | What it is |
|------|------------|
| `dialer_config.json` | Configuration with `deployment_mode: client` and your allowed slot count |
| `logs/crm.sqlite3` | Client database holding your single agent account |
| `data/gv_accounts.json` | Google Voice account details, if profiles were included |
| `chrome_profiles/` | Signed-in browser profiles for the voice lines |
| `CLIENT_SETUP.txt` | Plain-text instructions and a credentials summary |

To install:

1. Install the app on this PC — either the built EXE, or the Python source with
   `pip install -r requirements.txt`.
2. Copy **everything** from the export folder into the app directory. Merge `logs`, `data`,
   and `chrome_profiles` into the existing folders, and replace `dialer_config.json`.
3. Start the app. The first screen is **Agent sign-in** only.
4. Sign in with the email and password your administrator set during export.

If the app shows **"Workstation not configured"**, the `logs` folder from the package was not
copied correctly. Copy it again, replacing the existing one.

## Install from source

If you were given the source tree rather than an exported package:

```bash
pip install -r requirements.txt
python autodialer_gui.py
```

This starts in **administrator** mode. A client PC must always run with the exported
`dialer_config.json` (which sets `deployment_mode: client`) in place, otherwise the
administrator setup wizard appears instead of the sign-in screen.

## What you can do

- Sign in with your agent account
- Load an Excel contact list and run campaigns
- Place a manual **test call** on any line without starting a campaign
- Open the live browser panel on a line to hear and talk through the call
- Read call history and notes in the local CRM

## What you cannot do

On a client workstation, administrator features are not available even if an admin password is
entered:

- No **Settings** access to Google Voice accounts
- No **Administration** tab, so you cannot add users or export packages
- No access to other clients' lists, logs, or CRM history

Your slot count is fixed by the administrator at export time.

## Everyday use

1. Start the app and sign in.
2. Wait for each voice line to reach **Ready**. The app signs in automatically using the saved
   account details, so a brief delay on startup is normal.
3. Open the **Dialer** tab, browse to your Excel file, and click **Load contacts**.
4. Set **Lines at once** to your allowed slot count, then **Start dialing**.
5. Watch progress on the status bar, and open the **Logs** tab for per-call results.

## When something goes wrong

Check the support checklist in [docs/RUNBOOK.md](docs/RUNBOOK.md). It covers the common
failures:

- A line stuck in "Recovering line" — the watchdog is restarting it; let recovery finish.
- A blank Listen window — close and reopen it, then confirm system audio is unmuted.
- "Google Voice not ready" — re-connect the account under **Settings → Connect account** on
  the administrator PC and re-export the package.

Collect `logs/dialer.log` (last 50 lines), your number of active lines, your Windows version,
and whether the problem happens on a client package only or everywhere, before asking for help.

## Data on disk

| Path | Contents |
|------|----------|
| `data/gv_accounts.json` | Voice line emails and passwords — do not share |
| `chrome_profiles/` | Signed-in Google Voice sessions — do not share |
| `logs/crm.sqlite3` | Users, call history, notes |
| `logs/dialer.log` | Watchdog restarts, retries, errors |

Keep this PC private. Do not copy the `data` or `chrome_profiles` folders to anyone else.
