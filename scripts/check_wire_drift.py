#!/usr/bin/env python3
"""Check that TypeScript wire types are consistent with Python SQLModel fields.

Compares the field names in packages/web/src/lib/api/types.ts interfaces
against the Python SQLModel classes in src/kagan/core/models.py.

Exits 0 if consistent, 1 if drifted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TS_TYPES_FILE = REPO_ROOT / "packages" / "web" / "src" / "lib" / "api" / "types.ts"
MODELS_FILE = REPO_ROOT / "src" / "kagan" / "core" / "models.py"

# Map from TS interface name to Python model class name
INTERFACE_MAP: dict[str, str] = {
    "WireTask": "Task",
    "WireProject": "Project",
    "WireRepository": "Repository",
    "WireEvent": "SessionEvent",
}

# Fields only in TypeScript (runtime-computed, not in DB model)
TS_ONLY_FIELDS: dict[str, set[str]] = {
    "WireTask": {
        "last_event_at",
        "has_workspace",
        "review_running",
        "active_session",
    },
    "WireProject": {"active"},
    "WireRepository": {"selected"},
    "WireEvent": {"type"},  # renamed from event_type
}

# Fields only in Python (DB-internal, not surfaced to TS)
PY_ONLY_FIELDS: dict[str, set[str]] = {
    "Task": {"project_id", "created_at"},
    "Project": {"description", "created_at", "updated_at"},
    "Repository": {"scripts", "created_at", "updated_at"},
    "SessionEvent": {"task_id", "event_type"},  # event_type → renamed to "type" in TS
}


def _parse_ts_interfaces(text: str) -> dict[str, set[str]]:
    """Extract interface names and their field names from TypeScript source."""
    interfaces: dict[str, set[str]] = {}
    current: str | None = None
    brace_depth = 0

    for line in text.splitlines():
        # Match "export interface Foo {" or "export interface Foo extends Bar {"
        m = re.match(r"export\s+interface\s+(\w+)(?:\s+extends\s+\w+)?\s*\{", line)
        if m:
            current = m.group(1)
            interfaces[current] = set()
            brace_depth = 1
            continue

        if current is not None:
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                current = None
                continue
            # Match field lines like "  fieldName?: type;" or "  fieldName: type;"
            fm = re.match(r"\s+(\w+)\??:\s+", line)
            if fm:
                interfaces[current].add(fm.group(1))

    return interfaces


def _parse_py_model_fields(text: str) -> dict[str, set[str]]:
    """Extract SQLModel class names and their field names from Python source."""
    models: dict[str, set[str]] = {}
    current: str | None = None

    for line in text.splitlines():
        # Match "class Foo(SQLModel, table=True):"
        m = re.match(r"class\s+(\w+)\(SQLModel,\s*table=True\):", line)
        if m:
            current = m.group(1)
            models[current] = set()
            continue

        # End of class (a non-indented, non-blank, non-decorator line)
        if current and line and not line.startswith((" ", "\t", "#", "@")) and not line.strip() == "":
            current = None
            continue

        if current:
            # Match field definitions like "    field_name: Type = ..."
            fm = re.match(r"\s{4}(\w+):\s+", line)
            if fm:
                name = fm.group(1)
                # Skip dunder attributes and private attrs
                if not name.startswith("_"):
                    models[current].add(name)

    return models


def main() -> int:
    if not TS_TYPES_FILE.exists():
        print(f"SKIP: {TS_TYPES_FILE} not found")
        return 0

    if not MODELS_FILE.exists():
        print(f"ERROR: {MODELS_FILE} not found")
        return 1

    ts_interfaces = _parse_ts_interfaces(TS_TYPES_FILE.read_text())
    py_models = _parse_py_model_fields(MODELS_FILE.read_text())

    errors: list[str] = []

    for ts_name, py_name in INTERFACE_MAP.items():
        ts_fields = ts_interfaces.get(ts_name)
        py_fields = py_models.get(py_name)

        if ts_fields is None:
            errors.append(f"TypeScript interface {ts_name} not found in {TS_TYPES_FILE.name}")
            continue
        if py_fields is None:
            errors.append(f"Python model {py_name} not found in {MODELS_FILE.name}")
            continue

        ts_only_allowed = TS_ONLY_FIELDS.get(ts_name, set())
        py_only_allowed = PY_ONLY_FIELDS.get(py_name, set())

        # Fields in TS but not in Python (and not in the allowed list)
        ts_extra = ts_fields - py_fields - ts_only_allowed
        # Fields in Python but not in TS (and not in the allowed list)
        py_extra = py_fields - ts_fields - py_only_allowed

        if ts_extra:
            errors.append(
                f"{ts_name}: TypeScript has fields not in Python model {py_name} "
                f"(add to PY model or TS_ONLY_FIELDS): {sorted(ts_extra)}"
            )
        if py_extra:
            errors.append(
                f"{ts_name}: Python model {py_name} has fields not in TypeScript "
                f"(add to TS interface or PY_ONLY_FIELDS): {sorted(py_extra)}"
            )

    if errors:
        print("Wire drift detected:")
        for error in errors:
            print(f"  ✗ {error}")
        return 1

    checked = [ts for ts in INTERFACE_MAP if ts in ts_interfaces]
    print(f"Wire drift check passed ({len(checked)} interfaces verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
