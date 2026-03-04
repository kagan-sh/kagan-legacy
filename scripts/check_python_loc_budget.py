from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_MAX_LINES = 2500
EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
    "build",
    "dist",
    "__pycache__",
    "references",
}


def _iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def _line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enforce a per-file Python LOC budget.",
    )
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root to scan")
    parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help="Maximum allowed lines per Python file",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    files = _iter_python_files(root)
    if not files:
        print(f"No Python files found under {root}")
        return 0

    counts: list[tuple[Path, int]] = [(path, _line_count(path)) for path in files]
    offenders = [(path, count) for path, count in counts if count > args.max_lines]
    max_file, max_count = max(counts, key=lambda item: item[1])

    print(
        "LOC budget check: "
        f"files={len(counts)} max_lines={args.max_lines} highest={max_count} "
        f"file={max_file.relative_to(root)}"
    )

    if not offenders:
        print("All Python files are within the LOC budget.")
        return 0

    print("Files over LOC budget:")
    for path, count in sorted(offenders, key=lambda item: item[1], reverse=True):
        print(f"  {count:5d}  {path.relative_to(root)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
