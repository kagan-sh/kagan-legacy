---
title: Use GitHub Models
description: Run Kagan agents against 40+ models for free via GitHub Models
icon: material/github
tags:
  - github
  - models
  - llm
---

# Use GitHub Models

[GitHub Models](https://github.com/marketplace/models) provides free API access to 40+ AI models from OpenAI, Meta, Mistral, DeepSeek, and others. The API is OpenAI-compatible, so Kagan agent backends that support custom endpoints can use it with zero code changes.

## What you need

- A GitHub account (any tier — free works)
- A [personal access token](https://github.com/settings/tokens) with the `models:read` scope
- At least one Kagan agent backend installed

## Configure a backend

Backends that accept OpenAI-compatible endpoints work with GitHub Models out of the box. Set these environment variables before launching Kagan:

```bash
export OPENAI_BASE_URL=https://models.github.ai/inference
export OPENAI_API_KEY=ghp_your_token_here
```

Backend-specific additions:

| Backend | Extra env vars |
| ------- | -------------- |
| Goose | `GOOSE_PROVIDER=openai GOOSE_MODEL=openai/gpt-4.1` |
| OpenCode | Select model in OpenCode's own config |
| Codex | None — base URL + key is sufficient |

## Available models

Model IDs use `publisher/name` format:

| Model ID | Tier | Best for |
| -------- | ---- | -------- |
| `openai/gpt-4.1` | high | Complex reasoning, large codebases |
| `openai/gpt-4.1-mini` | low | Fast general-purpose coding |
| `mistral-ai/codestral-2501` | low | Code generation |
| `deepseek/deepseek-r1` | custom | Step-by-step reasoning |
| `meta/llama-4-scout-17b-16e-instruct` | high | Long-context open-weight |

Full catalog: <https://github.com/marketplace/models>

## Free tier limits

Limits depend on model tier. Every GitHub account gets:

| Tier | Requests/day | Requests/min | Tokens/request |
| ---- | ------------ | ------------ | -------------- |
| Low | 150 | 15 | 8K in / 4K out |
| High | 50 | 10 | 8K in / 4K out |
| Embeddings | 150 | 15 | 64K in |

Copilot Pro/Business/Enterprise subscribers get higher limits. Pay-as-you-go billing is available for production workloads.

## Troubleshooting

- `401 Unauthorized` — your token is missing or lacks the `models:read` scope. Regenerate it at <https://github.com/settings/tokens>.
- `429 Too Many Requests` — free tier quota exceeded. Wait for the daily reset or [enable paid usage](https://docs.github.com/en/billing/managing-billing-for-your-products/about-billing-for-github-models).
- `Model not found` — use the full `publisher/model` format, for example `openai/gpt-4.1` not just `gpt-4.1`.
- Slow responses — some models (DeepSeek-R1, Grok-3) have low concurrency limits on the free tier. Try a low-tier model for faster iteration.

## Prompt evaluation

Export resolved prompts and benchmark them with [promptfoo](https://promptfoo.dev).

### Export

```bash
kagan tools prompts export --type orchestrator --format text > prompt.txt
kagan tools prompts export --type orchestrator -o orchestrator.prompt.yml
```

Types: `orchestrator`, `execution`, `review`. Formats: `yml` (GitHub Models `.prompt.yml`) or `text` (raw).

### Evaluate locally

```bash
uv run poe eval          # generate prompts + run 12-test suite
uv run poe eval-view     # open results in browser
```

The eval suite resolves the strongest documented free GitHub Models default
available to your token, preferring `openai/gpt-4.1`. See `evals/README.md` for
details.
