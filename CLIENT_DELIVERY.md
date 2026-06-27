# Client Delivery Guide — Indus Transports Auto Dialer

Do **not** hand the client this editable development folder as the final product.

Use one of these delivery models:

## Recommended now: Packaged Windows EXE + client package

### On your PC (administrator)

1. Run **`Build Auto Dialer.bat`** (or `python build.py`).
2. Test `dist\IndusTransports_AutoDialer.exe`.
3. In the app: **Settings** → add and connect Google Voice lines.
4. **Administration** → **Export client package…** for each agent.
5. Deliver to the client:
   - `IndusTransports_AutoDialer.exe` (from `dist\`)
   - Contents of the exported client package folder
   - `Install Indus Transports Auto Dialer.bat` (optional, for shortcut setup)
   - `CLIENT.md` (usage instructions)

### On the client PC

1. Run the installer bat **or** copy files into e.g. `C:\IndusTransports\AutoDialer`.
2. Merge the exported package (config, logs, data, chrome_profiles).
3. Run the EXE. Agent sign-in only.

The client should **not** receive Python source, `.env`, or your admin password.

## Alternative: Hosted portal (planned)

Later you can manage subscriptions and deployments from a web portal. The app already stores per-user:

- `subscription_plan`
- `subscription_expires_at`
- `max_slots`

Client workstations use `deployment_mode: "client"` in `dialer_config.json` (set automatically by export).

## What not to deliver

- Raw git repo / development tree
- `chrome_profiles` from your admin PC mixed with unrelated accounts
- `.env` with `ADMIN_EMAIL` / `ADMIN_PASSWORD`
- `build/`, `dist/` build cache from your dev machine (only the final EXE)
- Test Excel files (`phones.xlsx`, etc.)

## Administrator checklist

| Step | Action |
|------|--------|
| 1 | Build EXE with `Build Auto Dialer.bat` |
| 2 | Configure GV lines in Settings |
| 3 | Create agent user in Administration |
| 4 | Export client package |
| 5 | Copy EXE + package to client PC |
| 6 | Send agent email/password only |

## Support files in this repo

| File | Purpose |
|------|---------|
| `build.py` | Build `dist\IndusTransports_AutoDialer.exe` |
| `Build Auto Dialer.bat` | Double-click build |
| `Install Indus Transports Auto Dialer.bat` | Client installer |
| `IndusTransports-Client-Setup.ps1` | PowerShell install logic |
| `Start Auto Dialer.bat` | Launch EXE or Python |
| `Repair Start.bat` | Clear cache + reinstall deps |
| `scripts/prepare_client_install.py` | CLI export (same as Administration UI) |
| `CLIENT.md` | End-user instructions |
