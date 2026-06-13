# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| main    | Yes       |

## Reporting a vulnerability

Please **do not** open public issues for security problems.

Contact the maintainer via the WhatsApp link in [README.md](README.md) or email your FT Solutions administrator.

Include:

- Affected component (dialer UI, Google Voice integration, CRM, etc.)
- Steps to reproduce
- Impact assessment

We aim to acknowledge reports within 3 business days.

## Safe deployment

- Keep `dialer_config.json` and `data/gv_accounts.json` out of git.
- Use **client export** for agent PCs instead of sharing admin credentials.
- Run on trusted Windows machines with disk encryption where possible.
