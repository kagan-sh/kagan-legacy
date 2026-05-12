#!/usr/bin/env bash
# Generate prompt files for promptfoo evaluation.
# Requires: kagan installed (uv sync --dev)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$SCRIPT_DIR/prompts"
mkdir -p "$OUT_DIR"

for prompt_type in orchestrator execution review; do
  uv run kagan tools prompts export --type "$prompt_type" --format text > "$OUT_DIR/$prompt_type.txt"
  echo "Wrote $OUT_DIR/$prompt_type.txt"
done
