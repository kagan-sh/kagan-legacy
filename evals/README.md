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

`github:openai/gpt-5-mini` at `temperature: 0`, `seed: 42`.

Cheapest GitHub Models tier. Good behavior here is a strong lower-bound.
Requires `GITHUB_TOKEN` with `models:read` scope.

## CI

Runs on PRs that touch `src/kagan/core/_prompts.py` or `evals/`, gated to `aorumbayev` and `kagan-agent`.

## Adding tests

```yaml
- description: "What this verifies"
  vars:
    system_prompt: file://prompts/orchestrator.txt  # or review.txt, execution.txt
    user_message: "The user input"
  assert:
    - type: icontains-any
      value: [expected, words]
```
