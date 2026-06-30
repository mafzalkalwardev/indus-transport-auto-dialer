# Client Run Guide — Indus Transports Auto Dialer

## Start the software

Double-click:

```text
Start Auto Dialer.bat
```

Or use the **Indus Transports Auto Dialer** desktop shortcut created by the installer.

If you received the packaged build, you can also run:

```text
IndusTransports_AutoDialer.exe
```

## First-time setup (client PC)

Your administrator configures Google Voice lines on their PC, then sends you a **client package** folder. Copy these into your install folder (merge/replace):

- `dialer_config.json`
- `logs\`
- `data\`
- `chrome_profiles\`

Then start the app. You will see **Agent sign-in only** — no administrator setup.

## Login

Use the **email and password** your administrator gave you. You cannot add Google Voice accounts or manage other users.

## Daily use

1. Sign in.
2. **Dialer** tab → load your Excel contact list or CRM contacts.
3. Click **Start dialing**.
4. **Live Calls** tab → click **Listen** on a line when you need to hear the call.
5. **Call Logs** and **CRM** tabs store your activity locally.

## Subscription

If your plan expires, sign-in will be blocked. Contact your administrator to renew.

## Troubleshooting

If the app will not start or feels slow:

```text
Repair Start.bat
```

This clears temporary cache, recreates runtime folders, and reinstalls Python packages (source installs only).

If calls get stuck on voicemail or the dialer stops advancing, contact your administrator — they may need to run an updated build or line recovery from the admin PC.

For help, contact your administrator or FT Solutions: +92 307 967 0503 (WhatsApp).
