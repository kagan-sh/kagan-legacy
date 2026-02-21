from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from kagan.core.domain.enums import TaskStatus, TaskType
from kagan.core.safety import (
    QUEUE_MESSAGE_MAX_CHARS,
    normalize_untrusted_text,
    redact_sensitive_text,
)

SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_AGENT_ERROR_PREFIX = re.compile(
    r"^(?:error|agent error|agent failed|failure)\s*:\s*",
    re.IGNORECASE,
)
_SESSION_FAILURE_SNIPPETS: tuple[str, ...] = (
    "session not found",
    "unknown session",
    "no active session",
    "active session is unavailable",
    "failed to find session",
)
_SESSION_FAILURE_HINT = "Start a new session with `/new session`, then resend your request."


class ChatTargetKind(StrEnum):
    ORCHESTRATOR = "orchestrator"
    AUTO = "auto"
    PAIR = "pair"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class ChatTarget:
    key: str
    kind: ChatTargetKind
    label: str
    task_id: str | None = None


@dataclass(frozen=True, slots=True)
class TaskContext:
    task_id: str
    short_id: str
    title: str
    task_type: TaskType | None
    status: TaskStatus | None


@dataclass(frozen=True, slots=True)
class DiscoveredSkill:
    name: str
    description: str
    location: Path
    source_root: Path


def trusted_skill_roots(project_root: Path) -> list[Path]:
    home = Path.home()
    candidates = [
        project_root / ".agents" / "skills",
        project_root / ".pi" / "skills",
        project_root / ".claude" / "skills",
        home / ".agents" / "skills",
        home / ".pi" / "skills",
        home / ".claude" / "skills",
        home / ".codex" / "skills",
        home / ".vtcode" / "skills",
    ]
    roots: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(resolved)
    return roots


def path_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def normalize_skill_description(raw: str, *, max_chars: int) -> str:
    normalized = normalize_untrusted_text(raw, max_chars=max_chars)
    redacted = redact_sensitive_text(normalized, redact_pii=True)
    return " ".join(redacted.split())


def parse_skill_frontmatter(text: str) -> dict[str, str]:
    # Normalize line endings so frontmatter parsing is consistent on Windows and POSIX.
    content = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if not content.startswith("---\n"):
        return {}
    terminator = "\n---"
    end_index = content.find(terminator, 4)
    if end_index == -1:
        return {}
    frontmatter = content[4:end_index]
    metadata: dict[str, str] = {}
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        normalized_key = key.strip().lower()
        if normalized_key not in {"name", "description"}:
            continue
        cleaned_value = value.strip().strip('"').strip("'")
        if cleaned_value:
            metadata[normalized_key] = cleaned_value
    return metadata


def extract_skill_metadata(
    skill_file: Path,
    *,
    root: Path,
    metadata_max_bytes: int,
    description_max_chars: int,
    skill_name_pattern: re.Pattern[str] = SKILL_NAME_PATTERN,
) -> DiscoveredSkill | None:
    resolved_file = skill_file.resolve(strict=False)
    if not path_within_root(resolved_file, root):
        return None
    if resolved_file.name != "SKILL.md":
        return None
    try:
        with resolved_file.open("rb") as handle:
            raw = handle.read(metadata_max_bytes)
    except OSError:
        return None

    metadata = parse_skill_frontmatter(raw.decode("utf-8", "replace"))
    skill_name = metadata.get("name", "").strip().lower()
    if not skill_name:
        skill_name = resolved_file.parent.name.strip().lower()
    if not skill_name_pattern.fullmatch(skill_name):
        return None
    description = normalize_skill_description(
        metadata.get("description", ""),
        max_chars=description_max_chars,
    )
    return DiscoveredSkill(
        name=skill_name,
        description=description,
        location=resolved_file,
        source_root=root,
    )


def discover_local_skills_for_roots(
    roots: list[Path],
    *,
    discovery_max_files: int,
    metadata_max_bytes: int,
    description_max_chars: int,
    skill_name_pattern: re.Pattern[str] = SKILL_NAME_PATTERN,
) -> list[DiscoveredSkill]:
    discovered: dict[str, DiscoveredSkill] = {}
    scanned_files = 0
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        try:
            candidates = sorted(root.rglob("SKILL.md"))
        except OSError:
            continue
        for skill_file in candidates:
            scanned_files += 1
            if scanned_files > discovery_max_files:
                break
            discovered_skill = extract_skill_metadata(
                skill_file,
                root=root,
                metadata_max_bytes=metadata_max_bytes,
                description_max_chars=description_max_chars,
                skill_name_pattern=skill_name_pattern,
            )
            if discovered_skill is None:
                continue
            if discovered_skill.name not in discovered:
                discovered[discovered_skill.name] = discovered_skill
        if scanned_files > discovery_max_files:
            break
    return sorted(discovered.values(), key=lambda item: item.name)


def task_value(task: object, key: str) -> object:
    if isinstance(task, dict):
        return task.get(key)
    return getattr(task, key, None)


def task_id(task: object) -> str | None:
    value = task_value(task, "id")
    if value is None:
        value = task_value(task, "task_id")
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def task_short_id(task: object) -> str:
    short_id = task_value(task, "short_id")
    if isinstance(short_id, str) and short_id:
        return short_id
    normalized_task_id = task_id(task) or "unknown"
    return normalized_task_id[:8]


def task_title(task: object, *, max_chars: int = 44) -> str:
    title = str(task_value(task, "title") or "").strip()
    if not title:
        return "Untitled task"
    if len(title) <= max_chars:
        return title
    return title[:max_chars] + "…"


def task_type_is(task: object, expected: TaskType) -> bool:
    value = task_value(task, "task_type")
    if value == expected:
        return True
    if isinstance(value, str):
        return value.lower() == expected.value
    return getattr(value, "value", None) == expected.value


def task_type(task: object) -> TaskType | None:
    value = task_value(task, "task_type")
    if isinstance(value, TaskType):
        return value
    normalized: str | None = None
    if isinstance(value, str):
        normalized = value.strip().lower()
    else:
        enum_value = getattr(value, "value", None)
        if isinstance(enum_value, str):
            normalized = enum_value.strip().lower()
    if normalized is None:
        return None
    for member in TaskType:
        if normalized == member.value:
            return member
    return None


def task_status(task: object) -> TaskStatus | None:
    value = task_value(task, "status")
    if isinstance(value, TaskStatus):
        return value
    normalized: str | None = None
    if isinstance(value, str):
        normalized = value.strip().lower()
    else:
        enum_value = getattr(value, "value", None)
        if isinstance(enum_value, str):
            normalized = enum_value.strip().lower()
    if normalized is None:
        return None
    for member in TaskStatus:
        if normalized == member.value:
            return member
    return None


def task_context(task: object) -> TaskContext | None:
    normalized_task_id = task_id(task)
    if not normalized_task_id:
        return None
    return TaskContext(
        task_id=normalized_task_id,
        short_id=task_short_id(task),
        title=task_title(task),
        task_type=task_type(task),
        status=task_status(task),
    )


def build_auto_follow_up_payload(text: str) -> str:
    sanitized_text = redact_sensitive_text(
        normalize_untrusted_text(text, max_chars=QUEUE_MESSAGE_MAX_CHARS),
        redact_pii=True,
    )
    policy_lines = [
        "UNIVERSAL_CHAT_FOLLOW_UP",
        "Priority order:",
        "1) Address the latest user instruction first in your next response/output.",
        "2) Then continue task implementation.",
        "3) Keep task metadata edits aligned with the latest user instruction and task scope.",
    ]
    policy_lines.append("latest_user_instruction:")
    policy_lines.append(sanitized_text)
    return "\n".join(policy_lines)


def build_review_follow_up_payload(text: str) -> str:
    return redact_sensitive_text(
        normalize_untrusted_text(text, max_chars=QUEUE_MESSAGE_MAX_CHARS),
        redact_pii=True,
    )


def snapshot_preview(snapshot: str, *, max_chars: int) -> str:
    if len(snapshot) <= max_chars:
        return snapshot
    return snapshot[: max_chars - 1].rstrip() + "…"


def normalize_agent_failure_for_ui(raw_message: str) -> tuple[str, str | None]:
    message = raw_message.strip()
    if not message:
        return ("The agent stopped unexpectedly.", None)

    previous = ""
    while message and message != previous:
        previous = message
        message = _AGENT_ERROR_PREFIX.sub("", message).strip()

    normalized = message.strip()
    lowered = normalized.casefold()
    if any(snippet in lowered for snippet in _SESSION_FAILURE_SNIPPETS):
        return ("The active agent session is unavailable.", _SESSION_FAILURE_HINT)
    if "timeout" in lowered or "timed out" in lowered:
        return (
            "The agent timed out before finishing.",
            "Try a narrower prompt or resend your request.",
        )

    if normalized and normalized[0].islower():
        normalized = normalized[0].upper() + normalized[1:]
    return (normalized or "The agent stopped unexpectedly.", None)


__all__ = [
    "ChatTarget",
    "ChatTargetKind",
    "DiscoveredSkill",
    "TaskContext",
    "build_auto_follow_up_payload",
    "build_review_follow_up_payload",
    "discover_local_skills_for_roots",
    "normalize_agent_failure_for_ui",
    "snapshot_preview",
    "task_context",
    "task_type_is",
    "trusted_skill_roots",
]
