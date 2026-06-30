# Pre-Delivery QA Verification (Administrator)

Run this checklist **before** exporting a client package or handing off the EXE. All steps assume you have **written consent** to call the numbers used.

## 1. Unit tests

```powershell
cd "D:\Dispatch Softwares\Auto Dialer"
python -m pytest tests/ -q
```

**Pass:** `189 passed` (or current count with no failures).

## 2. Google Voice lines

| Check | How |
|-------|-----|
| At least 2 lines signed in | Settings → each line shows ready; `chrome_profiles/<name>/.gv_session_ok` exists |
| Recommended for QA | **Johnson** + **Barry** (Shared may fail headless sign-in) |
| Louis | Sign in manually if you need a 3rd distinct account |

## 3. CRM sustained live test (recommended)

Headless test using **fresh CRM numbers only** — never re-dials numbers from prior reports.

Double-click **`Run CRM Sustained Test.bat`** or:

```powershell
python scripts/deep_live_test.py --min-minutes 7 --max-parallel 3 --skip-pytest --confirm "I OWN OR HAVE PERMISSION TO CALL THESE NUMBERS"
```

**Pass criteria:**

| Metric | Expected |
|--------|----------|
| Verdict | `PASS — sustained CRM live test with unique numbers` |
| Duration | ≥ 7 minutes |
| Unique numbers | ≥ 5 (sequential mode); no duplicate dials |
| Failures | 0 `FAILED` / `LOGIN_REQUIRED` |
| Report | `logs/deep_live_test_YYYYMMDD_HHMMSS.json` + `_summary.json` |

**Stable settings on 8 GB Windows PCs:**

- `--max-parallel 3` (Johnson, Barry, one cloned profile)
- Do **not** use `--force-parallel-dial` (concurrent WebEngine dial crashes on typical hardware)
- Sequential mode: one active call at a time across all loaded lines

## 4. GUI smoke (optional)

```powershell
python autodialer_gui.py
```

1. Load CRM contacts on **Dialer** tab.
2. Start with **1–2 lines** first.
3. Confirm: Ringing → Voicemail / No answer / Connected states update correctly.
4. Confirm hangup and next number without stuck slots.

## 5. Build and export

1. `Build Auto Dialer.bat` → `dist\IndusTransports_AutoDialer.exe`
2. Administration → **Export client package…**
3. Deliver per [CLIENT_DELIVERY.md](../CLIENT_DELIVERY.md)

## 6. What to send the client

| Include | Exclude |
|---------|---------|
| `IndusTransports_AutoDialer.exe` | Python source, `.env`, git repo |
| Exported client package | Your admin `chrome_profiles` mixed with unrelated accounts |
| `CLIENT.md` | `phones_test.xlsx`, test logs with real numbers |
| `Install Indus Transports Auto Dialer.bat` | `data/gv_accounts.json` with admin passwords |

## Latest verified run (reference)

- **Date:** 2026-06-29
- **Mode:** 3-line sequential CRM, 7 min
- **Result:** PASS — 10 unique numbers, 6 VOICEMAIL, 2 NO_ANSWER, 1 BUSY, 1 CONNECTED
- **Report:** `logs/deep_live_test_20260629_181447.json`

Update this section after each major release QA.
