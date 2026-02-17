"""Validate that documented paths, commands, and references are accurate.

This test catches docs drift — stale references to files, poe tasks, or CLI
commands that no longer exist. It runs as part of CI to prevent regressions.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Markdown files to scan for references
DOCS_GLOBS = ["docs/**/*.md", "*.md", "tests/README.md", ".github/**/*.md"]

# Poe task names extracted from pyproject.toml
_POE_TASK_RE = re.compile(r"^\[tool\.poe\.tasks(?:\.(\S+))?\]", re.MULTILINE)
_POE_INLINE_RE = re.compile(r"^(\w[\w-]*)\s*=", re.MULTILINE)


def _get_poe_task_names() -> set[str]:
    """Parse pyproject.toml to extract all defined poe task names."""
    pyproject = ROOT / "pyproject.toml"
    text = pyproject.read_text()

    tasks: set[str] = set()

    # Match [tool.poe.tasks.NAME] sections
    for m in _POE_TASK_RE.finditer(text):
        name = m.group(1)
        if name:
            tasks.add(name)

    # Match inline task definitions under [tool.poe.tasks]
    # Find the [tool.poe.tasks] section and extract inline keys
    section_match = re.search(r"^\[tool\.poe\.tasks\]\s*\n", text, re.MULTILINE)
    if section_match:
        section_start = section_match.end()
        # Read until the next [section] header
        next_section = re.search(r"^\[", text[section_start:], re.MULTILINE)
        section_end = section_start + next_section.start() if next_section else len(text)
        section_text = text[section_start:section_end]
        for m in _POE_INLINE_RE.finditer(section_text):
            tasks.add(m.group(1))

    return tasks


def _collect_md_files() -> list[Path]:
    """Collect all markdown files matching DOCS_GLOBS."""
    files: list[Path] = []
    for pattern in DOCS_GLOBS:
        files.extend(ROOT.glob(pattern))
    return sorted(set(files))


# --- Reference to poe tasks ---

_POE_CMD_RE = re.compile(r"uv run poe ([a-zA-Z][\w-]*)")


def _extract_poe_refs(path: Path) -> list[tuple[int, str]]:
    """Return (line_number, task_name) for each poe reference in a file."""
    refs: list[tuple[int, str]] = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        for m in _POE_CMD_RE.finditer(line):
            refs.append((i, m.group(1)))
    return refs


def test_poe_task_references_are_valid() -> None:
    """Every `uv run poe <task>` in docs must reference an existing poe task."""
    valid_tasks = _get_poe_task_names()
    errors: list[str] = []

    for md_file in _collect_md_files():
        for lineno, task_name in _extract_poe_refs(md_file):
            if task_name not in valid_tasks:
                rel = md_file.relative_to(ROOT)
                errors.append(f"{rel}:{lineno} references non-existent poe task '{task_name}'")

    assert not errors, "Stale poe task references found:\n" + "\n".join(errors)


# --- References to source paths ---

_SRC_PATH_RE = re.compile(r"`(src/kagan/\S+?)`")


def _extract_src_refs(path: Path) -> list[tuple[int, str]]:
    """Return (line_number, path_str) for each src/kagan/ reference."""
    refs: list[tuple[int, str]] = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        for m in _SRC_PATH_RE.finditer(line):
            refs.append((i, m.group(1)))
    return refs


def test_source_path_references_exist() -> None:
    """Every `src/kagan/...` backtick path in docs must exist in the repo."""
    errors: list[str] = []

    for md_file in _collect_md_files():
        for lineno, src_path in _extract_src_refs(md_file):
            # Normalize: remove trailing punctuation that might slip in
            clean = src_path.rstrip(".,;:)")
            # Skip glob patterns (e.g. operations/*)
            if "*" in clean:
                continue
            target = ROOT / clean
            if not target.exists():
                rel = md_file.relative_to(ROOT)
                errors.append(f"{rel}:{lineno} references non-existent path '{clean}'")

    assert not errors, "Stale source path references found:\n" + "\n".join(errors)


# --- References to doc paths ---

_DOC_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def _extract_doc_links(path: Path) -> list[tuple[int, str]]:
    """Return (line_number, link_target) for relative markdown links."""
    refs: list[tuple[int, str]] = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        for m in _DOC_LINK_RE.finditer(line):
            target = m.group(2)
            # Skip external URLs, anchors, and special protocols
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            refs.append((i, target))
    return refs


def test_relative_doc_links_resolve() -> None:
    """Relative markdown links in docs must resolve to existing files."""
    errors: list[str] = []

    for md_file in _collect_md_files():
        for lineno, link_target in _extract_doc_links(md_file):
            # Strip anchor fragments
            target_path = link_target.split("#")[0]
            if not target_path:
                continue

            # Resolve relative to the file's directory
            resolved = (md_file.parent / target_path).resolve()
            if not resolved.exists():
                rel = md_file.relative_to(ROOT)
                errors.append(f"{rel}:{lineno} links to non-existent '{target_path}'")

    assert not errors, "Broken relative links found:\n" + "\n".join(errors)


# --- Config file name consistency ---


def test_config_file_name_consistency() -> None:
    """Docs should reference 'config.toml' not 'kagan.toml' for the config file."""
    errors: list[str] = []

    for md_file in _collect_md_files():
        for i, line in enumerate(md_file.read_text().splitlines(), 1):
            if "kagan.toml" in line and "pyproject" not in line.lower():
                rel = md_file.relative_to(ROOT)
                errors.append(f"{rel}:{i} references 'kagan.toml' — should be 'config.toml'")

    assert not errors, "Config file name inconsistencies found:\n" + "\n".join(errors)
