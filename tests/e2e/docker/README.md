# Docker E2E Validation — Growth Bet 1 (DoctorModal + Install UX)

Validates the shipped feature (commit `32dcf1e`) against cold Linux installs.
**Not wired into CI.** Run manually before accepting the Growth Bet 1 milestone.

## What this tests

- `kagan doctor --json` output on a zero-ready Linux system (no backends).
- `kagan doctor --json` output when only the default backend (`claude-code`) is present.
- Real `npm install` of a backend (`codex`) and re-check flip from `warn` to `pass`.
- DOCTOR_WARNED telemetry row in the SQLite DB after a CLI doctor run.

## Requirements

- Docker (tested with 29.x)
- `jq`
- `sqlite3`
- Internet access for Scenario C (npm registry)

## Usage

```bash
cd tests/e2e/docker
./scenarios.sh
```

Skip the Docker image build step (reuse previously built images):

```bash
./scenarios.sh --no-build
```

## Images

| Image | Purpose |
|---|---|
| `kagan-e2e-base` | Zero-ready: Python 3.12 + uv + kagan, NO backend binaries |
| `kagan-e2e-default-installed` | Default backend (`claude-code` stub) present, 13 others absent |

## Scenarios

| Scenario | Image | Assert |
|---|---|---|
| A — Zero-ready | base | default=fail, 13+ others=warn, fix_hint non-empty |
| B — Default installed | default-installed | default=pass, 13+ others=warn, no fail entries |
| C — Real install | base | codex: warn→pass, DOCTOR_WARNED in telemetry DB |

## Coverage gaps

- **macOS / Windows** — not tested. Doctor output is Linux-only in these containers.
- **TUI DoctorModal paths** — auto-promote (`BACKEND_AUTO_PROMOTED`) requires `App.run_test`
  interaction; the CLI path deliberately does not auto-promote.
- **Backends requiring auth** — claude-code, codex, kimi-cli, github-copilot, auggie, amp
  all need API keys / OAuth after install. Only the binary presence is checked.
- **All 14 install commands live** — only `codex` (npm) is exercised in Scenario C.
  Other 13 are covered by `tests/unit/test_agent_registry.py` schema assertions.
