"""Allow ``python -m kagan.wire`` to export JSON Schema."""

import json

from kagan.wire.schema import export_schema

print(json.dumps(export_schema(), indent=2))
