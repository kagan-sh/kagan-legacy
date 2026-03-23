# Prompt Evaluations

Benchmark Kagan's default prompts with [promptfoo](https://promptfoo.dev).

## Quick start

```bash
uv run poe eval          # generate prompts + run suite
uv run poe eval-view     # open results in browser
```

## Design

12 tests, 12 API calls. Each test brings its own system prompt via `vars` — no prompt × test matrix.

| Prompt | Tests | Covers |
|--------|-------|--------|
| Orchestrator | 5 | identity + decomposition, clarification, safety, injection, structured planning |
| Review | 3 | protocol + tool calls, per-criterion verdicts, no-criteria edge case |
| Execution | 4 | commit checklist, scope enforcement, coordination, injection defense |

All assertions are deterministic (`icontains`, `not-icontains`). Zero LLM-judge cost.

## Model

`uv run poe eval` resolves the strongest documented free GitHub Models default
available to the current token. Preference order:
`openai/gpt-4.1` → `openai/gpt-4o` → `openai/gpt-4.1-mini` → `openai/gpt-4o-mini`.

`openai/gpt-4.1` is the primary default because GitHub documents it directly in
the API examples and catalog example, and describes it as stronger than
`gpt-4o`.

Requires `GITHUB_TOKEN` with `models:read` scope.

## CI

Runs on PRs that touch `src/kagan/core/_prompts.py` or `evals/`, gated to `aorumbayev` and `kagan-agent`.

The workflow runs promptfoo with `--max-concurrency 1 --delay 6500` so
`openai/gpt-4.1` stays under GitHub Models' free high-tier rate limits.

## Adding tests

```yaml
- description: "What this verifies"
  vars:
    system_prompt: file://prompts/orchestrator.txt
    user_message: "The user input"
  assert:
    - type: icontains-any
      value: [expected, words]
```
