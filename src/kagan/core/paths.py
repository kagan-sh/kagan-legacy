"""One canonical path/scope matcher (DESIGN §2/§3.6).

Three concerns that used to live in three modules with three slightly-different
implementations, now in one place so the gate, drift detection, and debt all
agree on what is in scope, what kagan wrote itself, and what the agent must never
touch:

  - ``matches_scope`` — the one scope matcher: a path is in scope if it matches a
    glob (``src/**``) OR sits under a bare prefix (``src/``). Both forms appear in
    real ``repo.yaml`` scopes, so a matcher that handled only one mis-flagged the
    other (a bare-prefix scope ``src/`` read as a 6-char literal no path begins
    with; a glob ``src/**`` invisible to ``str.startswith``).
  - ``RUN_ARTIFACTS`` / ``is_run_artifact`` — files KAGAN ITSELF writes into the
    worktree during a run (the MCP config, the prompt, the ask channel, the agent
    log). They are scaffolding, not agent work, so they are stripped from a diff
    BEFORE drift detection runs. Stripping the diff (not the findings) is what lets
    ``PROTECTED_PATHS`` tampering still surface — see ``reports.detect_drift``.
  - ``PROTECTED_PATHS`` — files the agent must NEVER edit even inside scope: the
    review contract (``.kagan/repo.yaml``) and the intake decision record
    (``.kagan/decisions*``). An agent edit to these is real tampering and must flag
    as drift; they are NOT run-artifacts, so they are never stripped.
"""

import fnmatch
from pathlib import Path

# Files kagan writes into a worktree during a run (see core/agent.py: prompt.txt,
# ask, agent.log; core/harness.py: .mcp.json). Stripped from a diff before drift
# detection so kagan's own scaffolding never reads as agent work.
RUN_ARTIFACTS: tuple[str, ...] = (
    ".mcp.json",
    ".kagan/ask",
    ".kagan/prompt*",
    ".kagan/agent.log",
)

# Files the agent must never edit, even inside declared scope (MCP-SEC, MCP-DRIFT):
# the shared review contract and the intake decision record. An agent edit here is
# tampering — it must flag as drift, so these are PROTECTED, never run-artifacts.
PROTECTED_PATHS: tuple[str, ...] = (
    ".kagan/repo.yaml",
    ".kagan/decisions*",
)


def glob_match(path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    """True if ``path`` matches any fnmatch glob in ``patterns``."""
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def matches_scope(path: str, scope: tuple[str, ...] | list[str]) -> bool:
    """The one true scope matcher: a glob (``src/**``) match OR a bare-prefix
    (``src/``) match. A bare-prefix entry admits any path under that directory; a
    glob entry is matched with fnmatch. Empty scope entries are ignored."""
    patterns = [s for s in scope if s]
    if glob_match(path, patterns):
        return True
    for p in patterns:
        prefix = p.rstrip("*").rstrip("/")
        if prefix and path.startswith(prefix):
            return True
    return False


def is_run_artifact(path: str) -> bool:
    """True for a path kagan itself writes during a run (RUN_ARTIFACTS). Match on
    both the full path and the basename so a worktree-relative ``.mcp.json`` and a
    nested ``.kagan/prompt.txt`` both register."""
    return glob_match(path, RUN_ARTIFACTS) or glob_match(Path(path).name, RUN_ARTIFACTS)


def is_protected(path: str) -> bool:
    """True for a path the agent must never edit (PROTECTED_PATHS). The patterns
    are explicit (exact name or one glob), so fnmatch alone is the right, tight
    test — no bare-prefix widening."""
    return glob_match(path, PROTECTED_PATHS)


def ensure_gitignore_line(gitignore_path: Path, line: str) -> bool:
    """Idempotently ensure ``line`` is present in the .gitignore at
    ``gitignore_path``. Returns True if a line was added, False if the exact line
    was already there. Never clobbers an existing file: a missing file is created
    with the one line; an existing file is appended to (with a leading newline only
    when it does not already end in one). The match is exact on a stripped line."""
    want = line.strip()
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding="utf-8")
        if any(ln.strip() == want for ln in existing.splitlines()):
            return False
        sep = "" if existing.endswith("\n") or existing == "" else "\n"
        gitignore_path.write_text(f"{existing}{sep}{want}\n", encoding="utf-8")
        return True
    gitignore_path.parent.mkdir(parents=True, exist_ok=True)
    gitignore_path.write_text(f"{want}\n", encoding="utf-8")
    return True


__all__ = [
    "PROTECTED_PATHS",
    "RUN_ARTIFACTS",
    "ensure_gitignore_line",
    "glob_match",
    "is_protected",
    "is_run_artifact",
    "matches_scope",
]
