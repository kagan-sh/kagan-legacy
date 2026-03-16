#!/usr/bin/env bash
# Generate TypeScript types from Python wire-model JSON Schema.
#
# Usage: bash generate.sh
#
# Pipeline:
#   1. `python -m kagan.wire` exports {"version":"1","models":{...}} with per-model JSON Schema
#   2. A Python script converts each model's JSON Schema into TypeScript interfaces
#   3. Output lands in src/generated.ts; src/index.ts re-exports it
#
# If any step fails the manually-maintained src/index.ts remains the source of truth.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ── Step 1: Export JSON Schema from Python ──────────────────────────
cd "$REPO_ROOT"
echo "Exporting wire schema from Python…"
uv run python -m kagan.wire > "$SCRIPT_DIR/schema.json"

# ── Step 2: Generate TypeScript from JSON Schema ────────────────────
python3 -c "
import json, sys, textwrap

HEADER = '''/* eslint-disable */
/**
 * Auto-generated from kagan.wire JSON Schema.
 * DO NOT MODIFY BY HAND. Run \`bash generate.sh\` to regenerate.
 */
'''

def json_type_to_ts(prop: dict) -> str:
    \"\"\"Map a JSON Schema property to a TypeScript type string.\"\"\"
    # anyOf with null means T | null
    if 'anyOf' in prop:
        types = []
        for variant in prop['anyOf']:
            t = variant.get('type')
            if t == 'null':
                types.append('null')
            elif t == 'string':
                types.append('string')
            elif t == 'integer' or t == 'number':
                types.append('number')
            elif t == 'boolean':
                types.append('boolean')
            elif t == 'object':
                types.append('Record<string, unknown>')
            elif t == 'array':
                types.append('unknown[]')
            elif t is None and not variant:
                # empty schema {} means any
                types.append('unknown')
            else:
                types.append('unknown')
        return ' | '.join(types) if types else 'unknown'

    t = prop.get('type')
    if t == 'string':
        return 'string'
    if t in ('integer', 'number'):
        return 'number'
    if t == 'boolean':
        return 'boolean'
    if t == 'array':
        items = prop.get('items', {})
        return json_type_to_ts(items) + '[]'
    if t == 'object':
        if prop.get('additionalProperties') is True or prop.get('additionalProperties', None) is True:
            return 'Record<string, unknown>'
        return 'Record<string, unknown>'
    # Fallback for untyped (e.g. generic data in WireEnvelope)
    return 'unknown'

raw = json.load(open('$SCRIPT_DIR/schema.json'))
models = raw['models']

lines = [HEADER.strip(), '']

for name, schema in models.items():
    desc = schema.get('description', '')
    if desc:
        # Multi-line doc comment
        doc_lines = desc.split(chr(10))
        lines.append('/**')
        for dl in doc_lines:
            lines.append(' * ' + dl)
        lines.append(' */')

    props = schema.get('properties', {})
    required = set(schema.get('required', []))

    lines.append(f'export interface {name} {{')

    for pname, pschema in props.items():
        ts_type = json_type_to_ts(pschema)
        optional = '' if pname in required else '?'
        pdesc = pschema.get('description', '')
        if pdesc:
            lines.append(f'  /** {pdesc} */')
        lines.append(f'  {pname}{optional}: {ts_type};')

    lines.append('}')
    lines.append('')

# Add WireResponse type alias (present in manual index.ts)
lines.append('export type WireResponse = WireEnvelope;')
lines.append('')

with open('$SCRIPT_DIR/src/generated.ts', 'w') as f:
    f.write(chr(10).join(lines) + chr(10))

print(f'Generated {len(models)} interfaces → src/generated.ts', file=sys.stderr)
" 2>&1

echo "Done."
