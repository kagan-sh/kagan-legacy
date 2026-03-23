#!/usr/bin/env bash
# Generate prompt files for promptfoo evaluation.
# Requires: kagan installed (uv sync --dev)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$SCRIPT_DIR/prompts"
mkdir -p "$OUT_DIR"

for prompt_type in orchestrator execution review; do
  uv run kagan prompts export --type "$prompt_type" --format text > "$OUT_DIR/$prompt_type.txt"
  echo "Wrote $OUT_DIR/$prompt_type.txt"
done

# Build JSON chat-format files for promptfoo (system + user template)
for prompt_type in orchestrator execution review; do
  python3 -c "
import json, sys
content = open('$OUT_DIR/$prompt_type.txt').read()
messages = [
    {'role': 'system', 'content': content},
    {'role': 'user', 'content': '{{user_message}}'},
]
json.dump(messages, sys.stdout, indent=2)
" > "$OUT_DIR/$prompt_type.json"
  echo "Wrote $OUT_DIR/$prompt_type.json"
done
