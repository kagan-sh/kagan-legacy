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

Several Kagan backends accept an OpenAI-compatible base URL. Set these environment variables to point them at GitHub Models:

### Goose

```bash
export GOOSE_PROVIDER=openai
export OPENAI_BASE_URL=https://models.github.ai/inference
export OPENAI_API_KEY=ghp_your_token_here
export GOOSE_MODEL=openai/gpt-4.1
```

### OpenCode

```bash
export OPENAI_BASE_URL=https://models.github.ai/inference
export OPENAI_API_KEY=ghp_your_token_here
```

Then select your model in OpenCode's own configuration.

### Codex

```bash
export OPENAI_BASE_URL=https://models.github.ai/inference
export OPENAI_API_KEY=ghp_your_token_here
```

Set these before launching Kagan, or add them to your shell profile.

## Available models

Model IDs use the `publisher/name` format. A curated selection:

| Model ID | Tier | Context | Best for |
| -------- | ---- | ------- | -------- |
| `openai/gpt-4.1` | high | 1M | Complex reasoning, large codebases |
| `openai/gpt-4.1-mini` | low | 1M | Fast general-purpose coding |
| `openai/gpt-4o-mini` | low | 128K | Quick tasks, cost-sensitive |
| `meta/llama-4-scout-17b-16e-instruct` | high | 10M | Long-context open-weight model |
| `meta/llama-3.3-70b-instruct` | high | 128K | Strong open-weight coding |
| `mistral-ai/codestral-2501` | low | 256K | Code generation and completion |
| `deepseek/deepseek-r1` | custom | 128K | Step-by-step reasoning |
| `microsoft/phi-4` | low | 16K | Lightweight local-quality tasks |
| `cohere/cohere-command-a` | low | 128K | Instruction following |
| `xai/grok-3-mini` | custom | 128K | Reasoning with speed |

Browse the full catalog at <https://github.com/marketplace/models>.

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
kagan prompts export --type orchestrator --format text > prompt.txt
kagan prompts export --type orchestrator -o orchestrator.prompt.yml
```

Types: `orchestrator`, `execution`, `review`. Formats: `yml` (GitHub Models `.prompt.yml`) or `text` (raw).

### Evaluate locally

```bash
bash evals/generate-prompts.sh
npx promptfoo@latest eval -c evals/promptfooconfig.yaml
npx promptfoo@latest view
```

The bundled eval suite in `evals/` uses `gpt-5-mini` as a lower-bound benchmark — good behavior on the cheapest model means the prompts are robust. See the [evals README](https://github.com/kagan-sh/kagan/tree/main/evals) for details.
