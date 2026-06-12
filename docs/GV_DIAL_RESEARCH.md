# Google Voice web dialing — research notes

Google Voice has **no public call API**. This app uses embedded **QWebEngine** (Chromium) with persistent profiles — the same approach as Playwright/CDP automation projects, but in-process for a desktop dialer.

## Stable dial entry points

| Method | URL | Notes |
|--------|-----|--------|
| New call query | `https://voice.google.com/u/0/calls?a=nc,%2B1XXXXXXXXXX` | Pre-fills dialer; user/agent still clicks Call |
| Dial shortcut | `https://voice.google.com/dial/+1XXXXXXXXXX` | Documented shortcut; used as fallback in this app |
| UI keypad | Calls tab → enter number → Call | What `_js_dial()` automates |

References: [Google Voice Help — Make a call](https://support.google.com/voice/answer/3379129), [Stack Overflow — GV call URL](https://stackoverflow.com/questions/5526392).

## What other projects do

- **googlevoice-mcp** — system Chrome + Playwright over CDP, persistent profile, interactive login/2FA once.
- **Py-Google-Voice** — Selenium/undetected-chromedriver scraping (not used here; we use QWebEngine).
- **Ubiquity-style efficiency** — URL scheme + keyboard-first; we implement Enter-after-number and direct URL load.

## Implications for this dialer

1. **Persistent `chrome_profiles/`** — session survives restarts (like CDP persistent context).
2. **No headless** — Google Voice expects a “visible” page for WebRTC; we render off-screen at 800×600.
3. **Call start** — synthetic JS click + Enter + view-local QTest click (monitor dialog broke global coords — fixed).
4. **Low RAM** — 8 GB + many Chrome tabs → cap at 1 line (`src/system_profile.py`).

## Not recommended

- Scraping deprecated `voice/call/connect/` POST without `_rnr_se` token (breaks often).
- Playwright bundled browser only (detection); system profile is fine.
- Mass dialing / non-consented numbers.
