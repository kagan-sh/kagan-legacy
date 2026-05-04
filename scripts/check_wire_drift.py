#!/usr/bin/env python3
"""Check that generated TypeScript wire types are up to date with the Python source models.

Regenerates the TypeScript output from the full wire surface and compares it
against the checked-in generated file at packages/shared/api-client/src/wire.ts.

Exits 0 if consistent, 1 if drifted.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATED_TS = REPO_ROOT / "packages" / "shared" / "api-client" / "src" / "wire.ts"


def main() -> int:
    # Import the generator — needs project source and scripts dir on path
    sys.path.insert(0, str(REPO_ROOT / "src"))
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from generate_wire_types import generate_ts  # type: ignore[import-untyped]

    if not GENERATED_TS.exists():
        print(
            f"DRIFT: {GENERATED_TS} does not exist — run: "
            f"uv run python scripts/generate_wire_types.py -o {GENERATED_TS}"
        )
        return 1

    expected = generate_ts()
    actual = GENERATED_TS.read_text()

    if actual != expected:
        print(f"DRIFT: {GENERATED_TS} is out of date. Regenerate with:")
        print(f"  uv run python scripts/generate_wire_types.py -o {GENERATED_TS}")
        return 1

    print("Wire drift check passed (wire.ts matches Python source models)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
