"""The one canonical path/scope matcher (DESIGN §2/§3.6, Phase 10 Track A).

These pin the unification: ONE matcher handles both glob and bare-prefix scopes,
so the gate and drift detection can never diverge again; the RUN_ARTIFACTS /
PROTECTED_PATHS split is what lets kagan strip its own scaffolding from a diff
while still flagging an agent edit to the review contract.
"""

from pathlib import Path

from kagan.core.paths import (
    ensure_gitignore_line,
    is_protected,
    is_run_artifact,
    matches_scope,
)


def test_matches_scope_admits_glob():
    # A glob scope (src/**) must admit a nested file. str.startswith would read
    # "src/**" as a 6-char literal no path begins with, so this fails if the matcher
    # drops the fnmatch half.
    assert matches_scope("src/auth/login.py", ["src/**"])
    assert not matches_scope("docs/readme.md", ["src/**"])


def test_matches_scope_admits_bare_prefix():
    # A bare-prefix scope (src/) must admit any path under it. fnmatch alone would
    # miss this (no wildcard), so this fails if the matcher drops the prefix half.
    assert matches_scope("src/auth/login.py", ["src/"])
    assert matches_scope("src/main.py", ["src/"])
    assert not matches_scope("tests/test_main.py", ["src/"])


def test_matches_scope_handles_glob_and_prefix_in_one_helper():
    # The whole point of the unification: one call, both forms, mixed in one scope.
    scope = ["src/**", "lib/"]
    assert matches_scope("src/a/b.py", scope)
    assert matches_scope("lib/c.py", scope)
    assert not matches_scope("README.md", scope)


def test_matches_scope_ignores_empty_entries():
    assert not matches_scope("anything.py", ["", " "])


def test_run_artifacts_are_recognised():
    # The files kagan itself writes during a run — stripped from a diff, never drift.
    assert is_run_artifact(".mcp.json")
    assert is_run_artifact(".kagan/ask")
    assert is_run_artifact(".kagan/prompt.txt")
    assert is_run_artifact(".kagan/agent.log")


def test_protected_paths_are_not_run_artifacts():
    # repo.yaml / decisions are PROTECTED (agent must not touch), NOT run-artifacts:
    # they must survive the diff-strip so an edit to them still flags as drift.
    assert is_protected(".kagan/repo.yaml")
    assert is_protected(".kagan/decisions.json")
    assert not is_run_artifact(".kagan/repo.yaml")
    assert not is_run_artifact(".kagan/decisions.json")


def test_run_artifacts_are_not_protected():
    assert not is_protected(".mcp.json")
    assert not is_protected(".kagan/ask")


def test_ensure_gitignore_line_creates_missing_file(tmp_path: Path):
    gi = tmp_path / ".gitignore"
    assert ensure_gitignore_line(gi, "state/") is True
    assert gi.read_text() == "state/\n"


def test_ensure_gitignore_line_is_idempotent(tmp_path: Path):
    # Running twice adds exactly one entry — the worktree append must not pile up.
    gi = tmp_path / ".gitignore"
    ensure_gitignore_line(gi, ".kagan_worktrees/")
    added_again = ensure_gitignore_line(gi, ".kagan_worktrees/")
    assert added_again is False
    assert gi.read_text().count(".kagan_worktrees/") == 1


def test_ensure_gitignore_line_never_clobbers_existing(tmp_path: Path):
    # An existing hand-written .gitignore is appended to, not replaced.
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\n__pycache__/\n", encoding="utf-8")
    ensure_gitignore_line(gi, ".kagan_worktrees/")
    text = gi.read_text()
    assert "node_modules/" in text
    assert "__pycache__/" in text
    assert text.endswith(".kagan_worktrees/\n")


def test_ensure_gitignore_line_appends_newline_when_file_lacks_trailing(tmp_path: Path):
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/", encoding="utf-8")  # no trailing newline
    ensure_gitignore_line(gi, "state/")
    assert gi.read_text() == "node_modules/\nstate/\n"
