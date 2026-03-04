# Contributing to Kagan

Thanks for contributing.

## Quick Start

```bash
git clone https://github.com/aorumbayev/kagan.git
cd kagan
uv sync --dev
uv run poe install-local
uv run poe fix
uv run poe typecheck
uv run pytest tests/ -v
```

## Local CLI Install

- `uv run poe install-local` is a one-time editable install for your machine.
- After that, `kagan` points at your local repo checkout, so code changes are picked up automatically.
- Re-run `uv run poe install-local` only when you change packaging metadata or entry points (for example `pyproject.toml` `[project.scripts]` / dependencies), or if the tool install becomes stale.

## What to Submit

- Small, focused PRs
- Tests for behavior changes
- Clear commit messages that explain why

## Persona Preset Safety and Whitelist

Kagan supports importing persona presets from public GitHub repos.

- Imports are blocked for untrusted repos unless the user explicitly opts in with risk acknowledgment.
- Trusted repos come from:
  - project registry: `registry/persona_repo_whitelist.json`
  - user-local whitelist (settings)

If you want your repo added to the project registry whitelist:

1. Open a PR editing `registry/persona_repo_whitelist.json`
1. Add your repo as `owner/repo` in lowercase
1. Include a short note in the PR description:
   - what the preset contains
   - why it is safe to publish
   - how users can review it

Maintainers may remove entries at any time if trust signals change.

## Security Expectations

- Never include secrets or tokens in prompts
- Keep preset files human-reviewable JSON
- Prefer immutable references (commit SHA) when sharing exact versions
- Assume users will inspect source before import

## Documentation

- Architecture and feature specs live in `docs/internal/`
- User docs live in `docs/`
