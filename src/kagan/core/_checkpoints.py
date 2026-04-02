"""Session checkpoints — git-based snapshots for rewind capability."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from kagan.core.errors import WorktreeError

_CHECKPOINT_TAG_PREFIX = "kagan/checkpoint"


@dataclass(slots=True)
class Checkpoint:
    """A snapshot of session state at a point in time."""

    session_id: str
    step_index: int
    commit_sha: str
    tag_name: str
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "step_index": self.step_index,
            "commit_sha": self.commit_sha,
            "tag_name": self.tag_name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }


async def create_checkpoint(
    worktree_path: Path,
    session_id: str,
    step_index: int,
    description: str = "",
) -> Checkpoint | None:
    """Create a lightweight git tag as a checkpoint.

    Returns None if no commits exist or HEAD cannot be resolved.
    """
    from kagan.core.git import run_git

    try:
        sha = await run_git(["rev-parse", "HEAD"], cwd=worktree_path)
        sha = sha.strip()
    except Exception:
        logger.debug("No commits in worktree — skipping checkpoint")
        return None

    tag_name = f"{_CHECKPOINT_TAG_PREFIX}/{session_id}/{step_index}"

    try:
        await run_git(["tag", "-f", tag_name, sha], cwd=worktree_path)
    except Exception:
        logger.warning("Failed to create checkpoint tag {}", tag_name)
        return None

    checkpoint = Checkpoint(
        session_id=session_id,
        step_index=step_index,
        commit_sha=sha,
        tag_name=tag_name,
        description=description,
    )
    logger.info("Checkpoint created: {} → {}", tag_name, sha[:8])
    return checkpoint


async def list_checkpoints(
    worktree_path: Path,
    session_id: str,
) -> list[Checkpoint]:
    """List all checkpoints for a session, sorted by step index."""
    from kagan.core.git import run_git

    prefix = f"{_CHECKPOINT_TAG_PREFIX}/{session_id}/"
    try:
        output = await run_git(["tag", "--list", f"{prefix}*"], cwd=worktree_path)
    except Exception:
        return []

    checkpoints: list[Checkpoint] = []
    for raw_tag in output.strip().splitlines():
        tag_name = raw_tag.strip()
        if not tag_name:
            continue
        try:
            step_str = tag_name.removeprefix(prefix)
            step_index = int(step_str)
        except ValueError:
            continue

        try:
            sha = (await run_git(["rev-parse", tag_name], cwd=worktree_path)).strip()
        except Exception:
            continue

        checkpoints.append(
            Checkpoint(
                session_id=session_id,
                step_index=step_index,
                commit_sha=sha,
                tag_name=tag_name,
            )
        )

    checkpoints.sort(key=lambda c: c.step_index)
    return checkpoints


async def rewind_to_checkpoint(
    worktree_path: Path,
    checkpoint: Checkpoint,
) -> None:
    """Reset the worktree to a checkpoint's commit state."""
    from kagan.core.git import run_git

    if not Path(worktree_path).exists():
        raise WorktreeError(f"Worktree path does not exist: {worktree_path}")

    await run_git(["reset", "--hard", checkpoint.commit_sha], cwd=worktree_path)
    logger.info(
        "Rewound worktree to checkpoint {} ({})",
        checkpoint.tag_name,
        checkpoint.commit_sha[:8],
    )


async def cleanup_checkpoints(
    worktree_path: Path,
    session_id: str,
) -> int:
    """Remove all checkpoint tags for a session. Returns count removed."""
    checkpoints = await list_checkpoints(worktree_path, session_id)
    if not checkpoints:
        return 0

    from kagan.core.git import run_git

    removed = 0
    for cp in checkpoints:
        try:
            await run_git(["tag", "-d", cp.tag_name], cwd=worktree_path)
            removed += 1
        except Exception:
            logger.debug("Failed to remove checkpoint tag {}", cp.tag_name)

    return removed


__all__ = [
    "Checkpoint",
    "cleanup_checkpoints",
    "create_checkpoint",
    "list_checkpoints",
    "rewind_to_checkpoint",
]
