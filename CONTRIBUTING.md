# Contributing to Kagan

Thanks for contributing.

## Quick Start

```bash
git clone https://github.com/kagan-sh/kagan.git
cd kagan
uv sync --dev
uv run poe install-local
uv run poe fix
uv run poe typecheck
uv run pytest tests/ -v
```

## Local CLI Install

`uv run poe install-local` installs the CLI in editable mode. After that, `kagan` points to your local checkout. Re-run only when changing `pyproject.toml` metadata or entry points.

## What to Submit

- Small, focused PRs
- Tests for behavior changes
- Clear commit messages explaining why

## Persona Preset Safety

Kagan supports importing persona presets from public GitHub repos. Imports are blocked for untrusted repos unless the user opts in with risk acknowledgment.

Trusted repos are listed in:
- `registry/persona_repo_whitelist.json`
- User-local whitelist (settings)

To add your repo to the project registry, open a PR editing the whitelist JSON. Include: what the preset contains, why it is safe, and how users can review it.

## Security Expectations

- Never include secrets in prompts
- Keep preset files human-reviewable JSON
- Prefer immutable references (commit SHA) when sharing exact versions
- Assume users will inspect source before import

## Documentation

- Architecture and feature specs: `docs/internal/`
- User docs: `docs/`

If you change TUI controls, update: `src/kagan/tui/keybindings.py`, in-app hints/help, `docs/reference/keybindings.md`, and related tests.

Current chat-overlay controls: `Space` cycles split orientation, `Esc` closes, `Ctrl+F` opens fullscreen when overlay is visible.

If you change behavioral settings or prompt resolution, update: `src/kagan/core/_prompts.py`, the TUI settings modal, web settings panel, `docs/reference/configuration.md`, and AGENTS.md.

## Web Client Changes

If your PR touches `packages/web`, run these checks:

```bash
cd packages/web
pnpm run typecheck
pnpm run build
```

If bundled server assets are affected, also run:

```bash
uv run poe web-build
```
