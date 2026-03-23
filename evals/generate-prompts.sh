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

# Build JSON chat-format files for promptfoo (system + user template).
# Paths passed via sys.argv to avoid shell injection in inline Python.
for prompt_type in orchestrator execution review; do
  python3 - "$OUT_DIR/$prompt_type.txt" "$OUT_DIR/$prompt_type.json" <<'PYEOF'
import json, sys
content = open(sys.argv[1]).read()
messages = [
    {"role": "system", "content": content},
    {"role": "user", "content": "{{user_message}}"},
]
with open(sys.argv[2], "w") as f:
    json.dump(messages, f, indent=2)
PYEOF
  echo "Wrote $OUT_DIR/$prompt_type.json"
done
