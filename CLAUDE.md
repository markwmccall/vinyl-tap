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

## Planning

- **All code implementations require a written plan before any code is written.** No vibe coding.
- Plans live in `docs/plans/` as Markdown files (e.g. `docs/plans/feature-smapi-search.md`).
- A plan must be detailed enough that implementation requires no on-the-fly discovery. It should include:
  - Problem statement and goals
  - Files to create or modify, and what changes each requires
  - New functions/classes/routes and their signatures
  - Data flow and any state changes
  - Test cases that will be written
  - Any open questions resolved before coding starts
- Get explicit user approval of the plan before writing code.
- If discovery during implementation reveals something the plan missed, stop and update the plan before proceeding.

## Code Style

- Do not change punctuation, whitespace, or formatting in lines you are not otherwise modifying.
- In particular, never convert hyphens (`-`) to em-dashes (`—`) or make other typographic substitutions in existing strings.
