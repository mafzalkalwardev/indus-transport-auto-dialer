# Changelog

## v1.0.1 — 2026-06-29

### Added
- `scripts/deep_live_test.py` — CRM sustained live test (unique numbers, auto-refill, JSON reports)
- `Run CRM Sustained Test.bat` — administrator one-click QA
- `docs/QA_VERIFICATION.md` — pre-delivery checklist for client handoff
- `docs/releases/v1.0.1.md` — release notes
- `load_all_report_dialed_numbers()` — exclude previously tested numbers from CRM pool
- Parallel dial flag (`--force-parallel-dial`, off by default)
- Profile cloning for multi-slot QA (Johnson + Barry)

### Fixed
- Voicemail / no-answer slots stuck without hangup (smoke + GUI + GV controller)
- Triple voicemail hangup scheduling in live smoke runner
- Dial UI clear race (async JS callback)
- `call_click_no_panel` retry path and dial field reset between calls
- Sequential multi-line gate: wait for call completion; removed 25s timeout overlap
- WebEngine crash when two lines dialed concurrently on typical Windows RAM

### Changed
- Live smoke: staggered GV slot boot; optional duplicate lines for QA
- Deep test pass criteria adjusted for sequential mode (min 5 calls @ 3 lines)

## v1.0.0 — 2026-06-27

- Initial stable release documentation
- README compliance section and WhatsApp support contact
- Screenshot gallery in `docs/screenshots/`
- Client delivery docs: `CLIENT.md`, `CLIENT_DELIVERY.md`
