"""kagan.server.mcp.prompts — MCP prompt registrations."""

from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts.base import UserMessage

from kagan.core import resolve_review_prompt
from kagan.server.mcp.server import ServerOptions, get_server_context


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register all kagan MCP prompts — always available regardless of access tier."""

    async def _resolve_project_path(settings: dict[str, str]) -> Path | None:
        app = get_server_context(mcp)
        if app is None:
            return None
        pid = app.bound_project_id or app.client.active_project_id
        return await app.client.projects.resolve_repo_path(project_id=pid, settings=settings)

    @mcp.prompt()
    async def review_task(task_id: str) -> list[UserMessage]:
        """Return a structured code-review prompt for the given task."""
        app = get_server_context(mcp)
        settings = await app.client.settings.get() if app is not None else {}
        project_path = await _resolve_project_path(settings)
        prompt = resolve_review_prompt(task_id, settings, project_path)
        return [UserMessage(prompt)]

    @mcp.prompt()
    async def plan_tasks_from_description(description: str) -> list[UserMessage]:
        """Return a task-breakdown prompt for the given feature description."""
        return [
            UserMessage(
                f"Break down this feature into concrete tasks:\n\n{description}\n\n"
                "Per task: title (\u2264 10 words), 1-sentence description, "
                "2-6 verifiable acceptance criteria, dependency + parallelization "
                "notes, effort (small/medium/large), run preference "
                "(managed default; attached for interactive/debug/exploratory).\n\n"
                "Group independent non-overlapping tasks into concurrent waves; "
                "if overlap is uncertain, sequence them. Never run concurrent "
                "mutating work in the same workspace."
            )
        ]

    @mcp.prompt()
    async def diagnose_failure(task_id: str, failure_summary: str) -> list[UserMessage]:
        """Return a diagnostic prompt for a failed task."""
        return [
            UserMessage(
                f"Task {task_id} failed:\n\n{failure_summary}\n\n"
                "Diagnose: (1) most likely root cause, (2) concrete remediation, "
                "(3) retry or escalate."
            )
        ]

    @mcp.prompt()
    async def security_audit_persona_repo(
        repo: str, path: str = ".kagan/personas.json"
    ) -> list[UserMessage]:
        """Return a read-only audit prompt for a persona preset repository."""
        return [
            UserMessage(
                f"Audit persona preset source {repo} at {path}. Read-only auditor.\n\n"
                "DO: call `persona_inspect` first and quote findings verbatim; "
                "state whether repo is whitelist-trusted; recommend "
                "install / install-with-caution / reject; back every claim with "
                "evidence bullets tied to audit-output fields.\n"
                "DON'T: claim absolute safety; perform writes or imports; omit "
                "the disclaimer.\n\n"
                "Disclaimer (required): this audit is advisory and heuristic. "
                "User must review repository source before import."
            )
        ]
