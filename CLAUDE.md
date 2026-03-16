# Vinyl Emulator — Claude Code Instructions

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for architecture, hardware gotchas,
Sonos playback reference, and multi-service research notes.

## Git Workflow

- **Never commit directly to `main`**, even for single-line fixes.
- All changes go through a branch → PR → merge flow.
- Branch protection on `main` requires a PR and passing CI (`test` status check).
- Create a short-lived branch, commit, push, open PR — even for trivial changes.

## Testing

- Test command: `.venv/bin/python -m pytest tests/ -v`
- System `python3` has a stale Flask/werkzeug mismatch — always use the venv.
- Follow TDD: write failing tests first, then implement.
- All tests must pass before opening a PR.

## Commits

- Only commit when the user asks.
- Use a branch; never push directly to `main`.

## Code Style

- Do not change punctuation, whitespace, or formatting in lines you are not otherwise modifying.
- In particular, never convert hyphens (`-`) to em-dashes (`—`) or make other typographic substitutions in existing strings.
