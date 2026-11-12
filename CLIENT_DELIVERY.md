# Client Delivery Guide

How to package the auto dialer for a client PC and hand it over. Run these steps on the
**administrator** PC, where the Google Voice lines are already configured.

## Before you export

1. **Settings** → add each Google Voice line (email + password). Wait until every line shows
   **Ready**.
2. Confirm each line can place a manual **test call**. A line that cannot call will not work
   on the client PC either.
3. Confirm `dialer_config.json` holds the settings you want to ship.

You can also run a load test before a large rollout — see [docs/LOAD_TEST.md](docs/LOAD_TEST.md).

## Export a client package

### From the app

**Administration → Export client package…**

Enter:

| Field | Meaning |
|-------|---------|
| Client name | Display name shown in the app and stored in the client database |
| Login email | The agent's sign-in email |
| Login password | The agent's sign-in password, 8+ characters |
| Subscription | Pick **15 days**, **Weekly**, **Monthly**, or **No expiry**. The expiry date is calculated for you |
| Max live slots | Maximum simultaneous dialing slots for this client, 1–5 |
| Save folder | Where the package folder is created, e.g. Desktop |

You get a folder named `FTSolutions_AutoDialer_Client` containing:

- `dialer_config.json` — `deployment_mode: client`, with the client's slot limit
- `logs/crm.sqlite3` — a database with a single agent account
- `data/gv_accounts.json` and `chrome_profiles/` — the signed-in voice lines
- `CLIENT_SETUP.txt` — plain-text instructions and a credentials summary for the client

### From the command line

```bash
python scripts/prepare_client_install.py \
  --name "Jane Agent" \
  --email jane@example.com \
  --password "TheirPassword8" \
  --max-slots 3
```

Useful flags:

| Flag | Effect |
|------|--------|
| `--output` | Parent folder for the package (default `~/Desktop`) |
| `--no-profiles` | Do not copy `chrome_profiles`, so the client signs in manually |
| `--subscription-plan` | Plan label stored in the client database, e.g. `manual` |
| `--subscription-expires-at` | Expiry date/time, e.g. `2026-07-04` or `2026-07-04 23:59:59` |
| `--max-slots` | Maximum live dialing slots for this client, 1–5 |

The CLI takes the plan and expiry as free text, while the app dialog offers
**15 days**, **Weekly**, **Monthly**, and **No expiry** and computes the date for you.

Use `--no-profiles` when you do not want to hand over signed-in browser sessions. The client
then signs in manually on first run.

## Hand over

1. Copy the exported folder to the client PC.
2. On the client PC, install the app and copy **everything** from the export folder into the
   app directory — merge `logs`, `data`, and `chrome_profiles`, and replace
   `dialer_config.json`.
3. Start the app. The client sees **Agent sign-in** only.
4. Give the client **only** their email and password from the export step. Do not send your
   administrator password, and do not share your own `chrome_profiles` folder.

The client installs and signs in on their own — see [CLIENT.md](CLIENT.md) for the client-side
instructions you can forward to them.

## Administrator → client handoff checklist

- [ ] Every Google Voice line shows **Ready** on the administrator PC
- [ ] Each line passes a manual test call
- [ ] Client name, email, password, plan, expiry, and slot limit are set on the export dialog
- [ ] The export folder contains `dialer_config.json`, `logs/`, `data/`, `chrome_profiles/`, and `CLIENT_SETUP.txt`
- [ ] `dialer_config.json` in the package contains `deployment_mode: client`
- [ ] The client PC has the app installed at the same version as the administrator PC
- [ ] The export folder was copied into the app directory on the client PC, replacing `dialer_config.json`
- [ ] The client signs in successfully and sees no administrator tabs
- [ ] The client can load a contact list and place one test call
- [ ] The client received their email and password — and nothing else

## Verifying a delivered package

On the client PC, confirm:

```bash
python -c "import json;print(json.load(open('dialer_config.json'))['deployment_mode'])"
```

It must print `client`. If it prints `admin`, the wrong `dialer_config.json` is in place and the
client will see the administrator setup wizard instead of the sign-in screen.

## Revoking access

Access is per client and stored in that client's `logs/crm.sqlite3`. To revoke it:

1. On the administrator PC, open **Administration → Users** and deactivate the client account.
2. Delete the client's package folder and their copy of it.
3. Rotate the Google Voice account password on the administrator PC and re-export packages
   that still need access.

## Adding more clients later

Repeat the export steps for each client PC. Exporting a package does not disturb existing
client packages — each folder is independent.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Client sees the administrator setup wizard | The exported `dialer_config.json` was not copied over |
| Client sees "Workstation not configured" | The package `logs` folder was not copied correctly |
| Client cannot sign in | Confirm the email matches the export dialog and that the client database was copied |
| Client sees lines as not ready | The `chrome_profiles` folder was missing; sign in manually or re-export with profiles |
| Package is large | `chrome_profiles` holds browser profiles. Use `--no-profiles` to exclude them |
