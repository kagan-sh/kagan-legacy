"""Retro / compound-knowledge loop (lever 8) — append a learning to AGENTS.md.

The ONLY writer of the repo-root ``AGENTS.md``. kagan NEVER edits it silently:
this is reachable only behind an explicit human confirm on the ship/approve
surface (DESIGN lever 8 / §3.6). Stdlib file IO; create-or-append under a stable
heading so a human-edited file is never clobbered.
"""

from datetime import UTC, datetime
from pathlib import Path

_HEADING = "## kagan learnings"
_INTRO = (
    "<!-- Appended by `kagan` on approve, only with your confirmation. "
    "Compounding org knowledge (DESIGN lever 8). -->"
)


def append_learning(repo_root: str | Path, line: str) -> Path:
    """Append ``line`` as a dated bullet under the stable heading in
    ``<repo_root>/AGENTS.md``, creating the file (and heading) if absent.

    Returns the AGENTS.md path. Never rewrites existing content — appends only —
    so concurrent human edits above the heading survive."""
    text = line.strip()
    if not text:
        raise ValueError("refusing to append an empty learning to AGENTS.md")
    path = Path(repo_root) / "AGENTS.md"
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    bullet = f"- {date}: {text}\n"
    if not path.exists():
        path.write_text(f"{_HEADING}\n\n{_INTRO}\n\n{bullet}", encoding="utf-8")
        return path
    existing = path.read_text(encoding="utf-8")
    sep = "" if existing.endswith("\n") else "\n"
    if _HEADING in existing:
        path.write_text(existing + sep + bullet, encoding="utf-8")
    else:
        path.write_text(f"{existing}{sep}\n{_HEADING}\n\n{bullet}", encoding="utf-8")
    return path


__all__ = ["append_learning"]
