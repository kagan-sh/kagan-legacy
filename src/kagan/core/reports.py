import json
from pathlib import Path

from kagan.core.git import parse_diff_changed_files
from kagan.core.models import Finding, ReportMessage, Task
from kagan.core.paths import is_protected, matches_scope


def _ask_path(worktree: str | Path) -> Path:
    return Path(worktree) / ".kagan" / "ask"


def append_ask(worktree: str | Path, envelope: dict) -> Path:
    path = _ask_path(worktree)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(envelope) + "\n")
    return path


def read_ask(worktree: str | Path, offset: int = 0) -> list[ReportMessage]:
    path = _ask_path(worktree)
    if not path.exists():
        return []
    out: list[ReportMessage] = []
    for line in path.read_text().splitlines()[offset:]:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            out.append(
                ReportMessage(type=data.get("type", "unknown"), payload=data.get("payload", {}))
            )
        except json.JSONDecodeError:
            out.append(ReportMessage(type="raw", payload={"line": line}))
    return out


def summarize_learnings(task: Task) -> str | None:
    """Lever 8: a candidate one-line learning for AGENTS.md, distilled from the
    task's resolved decisions, drift causes, and recurring finding locations.

    Pure read of the Task model (no ledger/file IO) so it tests like detect_drift.
    Returns None when there is nothing worth recording — the surface then makes no
    retro offer (DESIGN lever 8: opt-in, never silent)."""
    parts: list[str] = []
    answered = [d for d in task.decisions if d.answer]
    if answered:
        decided = "; ".join(f"{d.question.rstrip('?')} -> {d.answer}" for d in answered)
        parts.append(f"decided: {decided}")
    drift = [c.message for c in task.drift_concerns if c.message]
    if drift:
        parts.append(f"watch: {'; '.join(drift)}")
    repeated = _recurring_locations(task.findings)
    if repeated:
        parts.append(f"recurring findings in {', '.join(repeated)}")
    if not parts:
        return None
    return " · ".join(parts)


def _recurring_locations(findings: list[Finding]) -> list[str]:
    # A location flagged by more than one finding is a pattern worth recording.
    counts: dict[str, int] = {}
    for f in findings:
        if f.location:
            counts[f.location] = counts.get(f.location, 0) + 1
    return [loc for loc, n in counts.items() if n > 1]


def detect_drift(task: Task, diff_text: str) -> list[Finding]:
    """Flag changed files that are tampering or out-of-scope.

    The caller (harness._harvest) strips kagan's own run-artifacts from the diff
    BEFORE this runs, so a path reaching here is genuine agent work: a PROTECTED
    edit is tampering (blocks even inside scope), an out-of-scope edit is drift.
    Both scope and protected matching go through the one canonical matcher."""
    findings: list[Finding] = []
    for idx, f in enumerate(parse_diff_changed_files(diff_text)):
        if is_protected(f):
            findings.append(
                Finding(
                    id=f"drift-protected-{idx}",
                    severity="blocking",
                    location=f,
                    message=f"edit touches protected path {f}",
                )
            )
        elif task.scope and not matches_scope(f, task.scope):
            findings.append(
                Finding(
                    id=f"drift-scope-{idx}",
                    severity="blocking",
                    location=f,
                    message=f"edit outside declared scope: {f}",
                )
            )
    return findings


__all__ = ["append_ask", "detect_drift", "read_ask", "summarize_learnings"]
