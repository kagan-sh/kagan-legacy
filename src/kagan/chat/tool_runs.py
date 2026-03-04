import contextlib
import json
import time
from dataclasses import dataclass


# Note: ToolRunRecord is intentionally mutable (no frozen=True).
# Fields are updated during tool execution (status, args, result, ended_at),
# and records are modified in-place by ToolRunTracker.ensure_tool_run().
@dataclass(slots=True)
class ToolRunRecord:
    tool_key: str
    display_id: str
    title: str
    status: str
    key_arg: str | None
    args: str | None = None
    result: str | None = None
    started_at: float = 0.0
    ended_at: float | None = None


class ToolRunTracker:
    _MAX_TOOL_RUNS = 200

    def __init__(self) -> None:
        self._tool_status_by_key: dict[str, str] = {}
        self._tool_runs_by_key: dict[str, ToolRunRecord] = {}
        self._tool_runs_by_display_id: dict[str, ToolRunRecord] = {}
        self._tool_run_order: list[str] = []
        self._tool_run_counter = 0

    def _prune_runs(self) -> None:
        overflow = len(self._tool_run_order) - self._MAX_TOOL_RUNS
        while overflow > 0:
            oldest_key = self._tool_run_order.pop(0)
            record = self._tool_runs_by_key.pop(oldest_key, None)
            if record is not None:
                self._tool_runs_by_display_id.pop(record.display_id, None)
            self._tool_status_by_key.pop(oldest_key, None)
            overflow -= 1

    def start_turn(self) -> None:
        self._tool_status_by_key = {}

    @staticmethod
    def tool_key(update: object) -> str:
        for attr in ("tool_call_id", "call_id", "id"):
            value = getattr(update, attr, None)
            if value:
                return str(value)
        title = getattr(update, "title", None) or getattr(update, "name", None)
        return str(title or "tool")

    @staticmethod
    def extract_tool_key_arg(update: object) -> str | None:
        key_priority = ("title", "name", "query", "path", "command", "task_id", "pattern")
        raw = ToolRunTracker.extract_tool_args(update)
        if raw is None:
            return None
        parsed: dict[str, object] | None = None
        if isinstance(raw, dict):
            parsed = {str(key): value for key, value in raw.items()}
        elif isinstance(raw, str) and raw.strip():
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    parsed = {str(key): value for key, value in obj.items()}
        if parsed is None:
            return None
        for key in key_priority:
            value = parsed.get(key)
            if value is not None:
                preview = str(value)[:60]
                return f"{key}: {preview}"
        return None

    @staticmethod
    def extract_tool_args(update: object) -> object | None:
        for attr in ("raw_input", "rawInput", "arguments", "args"):
            value = getattr(update, attr, None)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def extract_tool_result(update: object) -> object | None:
        for attr in ("raw_output", "rawOutput", "result", "output"):
            value = getattr(update, attr, None)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def serialize_payload(value: object | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True)
        except TypeError:
            return str(value)

    def status_for(self, tool_key: str) -> str | None:
        return self._tool_status_by_key.get(tool_key)

    def set_status(self, tool_key: str, status: str) -> None:
        self._tool_status_by_key[tool_key] = status

    def ensure_tool_run(
        self,
        *,
        update: object,
        title: str,
        key_arg: str | None,
    ) -> ToolRunRecord:
        tool_key = self.tool_key(update)
        existing = self._tool_runs_by_key.get(tool_key)
        if existing is not None:
            if title:
                existing.title = title
            if key_arg:
                existing.key_arg = key_arg
            return existing

        self._tool_run_counter += 1
        display_id = f"t{self._tool_run_counter:03d}"
        created = ToolRunRecord(
            tool_key=tool_key,
            display_id=display_id,
            title=title,
            status="started",
            key_arg=key_arg,
            started_at=time.monotonic(),
        )
        self._tool_runs_by_key[tool_key] = created
        self._tool_runs_by_display_id[display_id] = created
        self._tool_run_order.append(tool_key)
        self._prune_runs()
        return created

    @staticmethod
    def duration_text(record: ToolRunRecord) -> str:
        end = record.ended_at if record.ended_at is not None else time.monotonic()
        elapsed = max(0.0, end - record.started_at)
        return f"{elapsed:.2f}s"

    def tool_report(self, query: str | None) -> tuple[str, bool]:
        normalized = (query or "").strip()
        if not normalized:
            if not self._tool_run_order:
                return "No tool calls recorded in this session yet.", False
            lines = ["Recent tool calls:"]
            for tool_key in self._tool_run_order[-20:]:
                record = self._tool_runs_by_key[tool_key]
                summary = (
                    f"[{record.display_id}] {record.title} · {record.status}"
                    f" · {self.duration_text(record)}"
                )
                if record.key_arg:
                    summary = f"{summary} · {record.key_arg}"
                lines.append(summary)
            lines.append("Use /tool <id> to inspect full input/output.")
            return "\n".join(lines), False

        if normalized in self._tool_runs_by_display_id:
            record = self._tool_runs_by_display_id[normalized]
        else:
            prefix_matches = [
                candidate
                for display_id, candidate in self._tool_runs_by_display_id.items()
                if display_id.startswith(normalized)
            ]
            if len(prefix_matches) == 1:
                record = prefix_matches[0]
            elif len(prefix_matches) > 1:
                ids = ", ".join(match.display_id for match in prefix_matches)
                return f"Ambiguous tool id '{normalized}'. Matches: {ids}", False
            else:
                return f"No tool call found for '{normalized}'.", False

        lines = [
            f"Tool call {record.display_id}",
            f"Title: {record.title}",
            f"Status: {record.status}",
            f"Duration: {self.duration_text(record)}",
        ]
        if record.key_arg:
            lines.append(f"Key arg: {record.key_arg}")

        lines.append("")
        lines.append("Input:")
        lines.append(record.args if record.args else "(none)")
        lines.append("")
        lines.append("Output:")
        lines.append(record.result if record.result else "(none)")
        return "\n".join(lines), True
