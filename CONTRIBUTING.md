# Contributing

Thank you for improving FT Solutions projects.

## Development setup

1. Clone the repository and create a virtual environment.
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `dialer_config.example.json` to `dialer_config.json` for local settings.
4. Run tests: `python -m pytest tests/ -q`

## Pull requests

- Keep changes focused and tested.
- Update docs when behavior or config keys change.
- Do not commit secrets (`dialer_config.json`, credentials, Chrome profiles).

## Reporting issues

Use GitHub Issues with steps to reproduce, expected vs actual behavior, and RAM/line count if stability-related.
