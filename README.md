# INDUS TRANSPORTS LLC — Auto Dialer Pro

> Windows desktop auto dialer for Indus Transports LLC using Google Voice browser automation, branded UI, local logs, and resume-capable calling workflow.

---

## Features

- **Branded UI** — INDUS TRANSPORTS LLC header with company logo and dark professional theme
- **Two automation modes:**
  - **pyautogui** (screen coordinates) — works out of the box, no browser setup needed
  - **Browser DOM mode** (Selenium) — more reliable automation via Chrome remote debugging
- **Three calling modes:**
  - Manual — press `X` to hang up and go to next
  - Manual Next — click button to advance
  - Auto-Cut — fully automatic: dial → wait N seconds → hang up → repeat
- **Smart phone validation** — handles `+1XXXXXXXXXX`, `(XXX) XXX-XXXX`, `XXX-XXX-XXXX`, `XXX.XXX.XXXX`
- **Resume capability** — skips already-completed numbers when you reload the same Excel file
- **Call log statuses:** `STARTED`, `ENDED`, `SKIPPED_INVALID`, `FAILED`, `STOPPED`
- **Log search & filter** — filter by phone, date, or status in real time
- **WhatsApp support** button opens `https://wa.me/923079670503`
- **Builds to a single EXE** via PyInstaller with branded icon

---

## Screenshots

> *(Add screenshots here after first run)*

---

## Requirements

- Windows 10 / 11
- Python 3.8+
- Google Chrome (for Browser DOM mode — optional)
- A Google Voice account (user logs in manually — the app does not bypass login)

---

## Setup

### 1. Install Python dependencies

```bash
pip install ttkbootstrap pyautogui pynput pandas openpyxl Pillow pyperclip selenium pygetwindow
```

### 2. Run the app

```bash
python autodialer_gui.py
```

### 3. Configure screen coordinates (pyautogui mode)

1. Open Google Voice in your browser and log in
2. In the app go to the **Coordinates** tab
3. Click **Pick** for each field and click on the corresponding element in Google Voice
4. Click **Save All Settings**

### 4. OR use Browser DOM mode (Selenium — more reliable)

Launch Chrome with remote debugging enabled:

```batch
chrome.exe --remote-debugging-port=9222 --user-data-dir="%TEMP%\chrome-debug"
```

Then in the app:
1. Check **Browser DOM Mode** in Settings
2. Go to the **Coordinates** tab and click **Connect to Chrome**
3. Log into Google Voice manually in that Chrome window

> **The app does NOT bypass Google login, CAPTCHA, or 2FA. The user always logs in manually.**

---

## Excel File Format

Your spreadsheet must have a column named one of:

```
Phone  |  Mobile  |  Number  |  Tel  |  phone  |  cell
```

Supported number formats in the column:

| Format | Example |
|---|---|
| 10 digits | `3055551234` |
| E.164 | `+13055551234` |
| Parentheses | `(305) 555-1234` |
| Dashes | `305-555-1234` |
| Dots | `305.555.1234` |

---

## Build EXE

```bash
python build_exe.py
```

Output: `dist/IndusTransports_AutoDialer.exe`

The build script will:
1. Install all dependencies
2. Convert the company logo PNG to a Windows `.ico` file
3. Bundle the EXE with the branded icon and config

---

## Safety Note

This application:
- Does **not** bypass Google login, CAPTCHA, or 2FA
- Does **not** access any Google API credentials
- Does **not** store or transmit your Google account data
- Only automates visible browser/screen actions after the user has manually logged in
- Is intended for legal, authorized use by Indus Transports LLC staff

---

## Support

WhatsApp: [+923079670503](https://wa.me/923079670503)

---

## Project Structure

```
Auto Dialer/
├── autodialer_gui.py              ← Main application
├── build_exe.py                   ← Build script (creates EXE)
├── AutoDialer_Pro.spec            ← PyInstaller spec
├── dialer_config.json             ← Saved coordinates & settings
├── call_logs.csv                  ← Call history (auto-created)
├── logo.ico                       ← App icon (auto-created by build)
├── Indus_Transports_LLC__1_-removebg-preview (1).png
└── Indus Transports LLC (1).jpeg
```
