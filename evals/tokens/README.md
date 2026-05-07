# Token Cost Measurement

Offline, dependency-light measurement of Kagan's agent prompts — chars, words,
lines, and approximate tokens per prompt across three arms:

- **`__baseline__`** — empty prompt (control)
- **`__terse__`** — `"Answer concisely."` (control: generic terseness)
- **`__current__`** — the prompt actually shipped (orchestrator, review, attached
  worker, MCP prompts)

Pairs with `evals/promptfooconfig.yaml` (which measures *quality*). This script
measures *cost*. Honest delta is **`__current__` vs `__terse__`** — beating
baseline only proves the model needs *some* instructions, not that yours are
well-engineered.

## Run

```bash
uv run poe prompt-tokens                                # print current table
uv run poe prompt-tokens --out evals/tokens/snapshots/now.json
uv run poe prompt-tokens --diff evals/tokens/snapshots/pre_compression.json
```

## Tokenizer

Uses `tiktoken/cl100k_base` if installed, else a `chars/4` heuristic. For
**relative** deltas the heuristic is stable (±1–2pp). Absolute numbers are
±15%. Anthropic's exact tokenizer is proprietary; cl100k_base is the standard
public proxy.

## Adding a prompt

Add to the `collect()` dict in `measure.py`. If the prompt is built dynamically
(needs a Task etc.), add a stub builder above and feed it deterministic input —
measurement must be reproducible.

## Snapshot files

- `snapshots/pre_compression.json` — baseline captured before the
  `feat/prompt-compression-evals` rewrite. Reference for the compression PR.

## Why not promptfoo for this?

promptfoo runs the model and asserts on output. Token-cost questions
(`how many input tokens does this prompt cost?`) need no model call. Running
this is free and offline; running promptfoo costs API quota.
