from __future__ import annotations

import argparse
import math
import subprocess
from pathlib import Path


def _staged_added_files() -> set[str]:
    result = subprocess.run(
        ("git", "diff", "--staged", "--name-only", "--diff-filter=A"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return {line for line in result.stdout.splitlines() if line}


def _find_large_files(file_paths: list[str], *, maxkb: int, staged_added: set[str]) -> list[tuple[str, int]]:
    large_files: list[tuple[str, int]] = []
    for file_path in file_paths:
        if file_path not in staged_added:
            continue
        path = Path(file_path)
        if not path.is_file():
            continue
        size_kb = math.ceil(path.stat().st_size / 1024)
        if size_kb > maxkb:
            large_files.append((file_path, size_kb))
    return large_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail if any provided file exceeds max size in KB.")
    parser.add_argument("filenames", nargs="*", help="Files pre-commit provides.")
    parser.add_argument(
        "--maxkb",
        type=int,
        default=500,
        help="Maximum allowed file size in KB",
    )
    args = parser.parse_args()

    staged_added = _staged_added_files()
    large_files = _find_large_files(args.filenames, maxkb=args.maxkb, staged_added=staged_added)
    if not large_files:
        return 0

    for file_path, size_kb in large_files:
        print(f"{file_path} ({size_kb} KB) exceeds {args.maxkb} KB.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
