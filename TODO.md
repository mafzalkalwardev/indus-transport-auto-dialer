# TODO

## Completed (recent)

- [x] Low-RAM mode (1 line on 8 GB), deferred WebEngine boot, process cleanup
- [x] Fix Call button click when Listen monitor is open (view-local coords)
- [x] Alternate GV dial URLs (`?a=nc` + `/dial/+1…`)
- [x] CRM timestamps: dialed_at / ringing_at / connected_at
- [x] Campaign resume (saved contact index)
- [x] Stuck-dial auto-retry + manual **Retry dial** button
- [x] Sample list auto-creates via `prepare_test_dial.py`
- [x] GitHub Actions pytest workflow + `scripts/dev_cycle.ps1`
- [x] 49+ unit tests passing

## Call-state pipeline (next)

- [ ] Full VICIdial-style UI labels for CLASSIFYING_AUDIO / HUMAN_DETECTED states
- [ ] Structured per-call JSON log line (single terminal event)
- [ ] Confirm voicemail detector never runs during RINGING in fusion engine

## Deploy

- [ ] Push `main` to GitHub: `git push origin main` (1 commit ahead locally)
- [ ] Rebuild EXE when stable on test PC
