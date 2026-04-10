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
                f"Break down the following feature into concrete tasks:\n\n{description}\n\n"
                "For each task provide:\n"
                "- A short title (\u2264 10 words)\n"
                "- A one-sentence description\n"
                "- Acceptance criteria (2-6 bullets, concrete and verifiable)\n"
                "- Dependency notes (what must finish first, if anything)\n"
                "- Parallelization notes (what can run concurrently safely)\n"
                "- Estimated effort: small / medium / large\n"
                "- Run preference recommendation (optional): managed or attached\n"
                "  \u2022 managed (default): agent runs independently to completion. "
                "Best for well-defined, self-contained tasks with clear acceptance criteria.\n"
                "  \u2022 attached: agent runs interactively as co-pilot in a terminal session. "
                "Best for exploratory work, complex debugging, or tasks needing user guidance.\n"
                "Default to managed unless the task clearly benefits from interactive "
                "collaboration.\n\n"
                "Execution planning rules:\n"
                "- Group independent, non-overlapping tasks into concurrent waves.\n"
                "- If overlap is uncertain, run sequentially.\n"
                "- Never schedule concurrent mutating work on the same workspace."
            )
        ]

    @mcp.prompt()
    async def diagnose_failure(task_id: str, failure_summary: str) -> list[UserMessage]:
        """Return a diagnostic prompt for a failed task."""
        return [
            UserMessage(
                f"Task {task_id} failed with the following error:\n\n{failure_summary}\n\n"
                "Please diagnose the root cause:\n"
                "1. Identify the most likely cause of the failure.\n"
                "2. Suggest concrete remediation steps.\n"
                "3. Indicate whether the task should be retried or escalated."
            )
        ]

    @mcp.prompt()
    async def security_audit_persona_repo(
        repo: str, path: str = ".kagan/personas.json"
    ) -> list[UserMessage]:
        """Return a read-only audit prompt for a persona preset repository."""
        return [
            UserMessage(
                f"Audit persona preset source {repo} at path {path}.\n\n"
                "You are a read-only security auditor.\n"
                "MUST DO:\n"
                "- Call persona_inspect first and quote findings exactly.\n"
                "- Explicitly state whether repo is trusted by whitelist.\n"
                "- Recommend next action: install, install with caution, or reject.\n"
                "- Provide evidence bullets tied to audit output fields.\n\n"
                "MUST NOT DO:\n"
                "- Do not claim absolute safety.\n"
                "- Do not perform writes or imports during audit.\n"
                "- Do not omit due-diligence disclaimer.\n\n"
                "Required disclaimer:\n"
                "This audit is advisory and heuristic. "
                "User must review repository source before import."
            )
        ]
