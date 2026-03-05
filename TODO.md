# TODO

Items from code review. See commit history for context.

---


## Cleanup

- [ ] **player.py bare loop** - Running `python3 player.py` (no flags) creates a second `PN532NFC()` instance that conflicts with the `vinyl-web` NFC thread. Remove the loop or make it error out with a clear message. `--simulate` and `--read` are still useful and should be kept.
- [ ] **Stale docs** - `docs/ARCH_NFC_UNIFIED.md` and `docs/PLAN.md` describe the old two-process architecture and completed planning phases. Delete or archive.

