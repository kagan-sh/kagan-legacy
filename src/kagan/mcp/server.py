"""kagan.mcp.server — the report-channel MCP server factory.

Registers the seven v2 report tools (``report_intake_decisions``,
``report_needs_you``, ``report_smoke_tests``, ``report_drift``, ``report_findings``,
``report_comprehension_prompts``, ``report_done``) on a FastMCP stdio server. The
server holds no state of its own — each tool is scoped to a task and mutates the
ledger only through ``Harness`` (P7).
"""

import functools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from loguru import logger
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel

from kagan.core.api import Harness


class SmokeReport(BaseModel):
    behaviour: str
    service: str | None = None


class FindingReport(BaseModel):
    severity: str  # "blocking" | "question" | "nit"
    location: str
    message: str  # must state a concrete failure path — no speculative findings (lever 2)
    confidence: int | None = None  # validator self-rating 0-10
    status: str | None = None  # "VERIFIED" | "UNVERIFIED" | "TENTATIVE"


class ComprehensionPromptReport(BaseModel):
    key: str
    question: str


@dataclass(frozen=True, slots=True)
class ServerOptions:
    readonly: bool = False
    task_id: str | None = None
    data_dir: str | None = None
    project_id: str | None = None


@dataclass(frozen=True, slots=True)
class ServerContext:
    client: Harness
    opts: ServerOptions
    bound_task_id: str | None = None


def get_context(ctx: Context) -> ServerContext:
    """Extract ServerContext from the MCP lifespan context."""
    app = ctx.request_context.lifespan_context
    if isinstance(app, ServerContext):
        return app
    raise ValueError("MCP app context is not available")


@asynccontextmanager
async def _lifespan(opts: ServerOptions, _mcp: FastMCP) -> AsyncIterator[ServerContext]:
    from kagan.core.api import configure_logging, install_asyncio_subprocess_exception_filter

    configure_logging()
    install_asyncio_subprocess_exception_filter()
    client = Harness(data_dir=opts.data_dir)
    logger.debug("MCP lifespan: client initialized")
    ctx = ServerContext(client=client, opts=opts, bound_task_id=opts.task_id)
    try:
        yield ctx
    finally:
        logger.debug("MCP lifespan: shutting down")
        await client.aclose()


def _deref_tool_schemas(mcp: FastMCP) -> None:
    """Inline $ref/$defs in each tool's input schema (P7: strict clients reject $ref)."""

    def inline(node: Any, defs: dict[str, Any]) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                return inline(defs[ref.split("/")[-1]], defs)
            return {k: inline(v, defs) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [inline(v, defs) for v in node]
        return node

    for tool in mcp._tool_manager.list_tools():
        defs = tool.parameters.get("$defs", {})
        if defs:
            tool.parameters = inline(tool.parameters, defs)


def create_server(opts: ServerOptions) -> FastMCP:
    """Create the kagan MCP server with the seven v2 report-channel tools."""
    instructions = (
        "Kagan — supervision-layer MCP server. Use the report tools to send intake "
        "decisions, the one needs-you interrupt, smoke tests, drift concerns, review "
        "findings, comprehension prompts, and a completion hint. Each report is scoped "
        "to a single task."
    )
    mcp = FastMCP(
        name="kagan", instructions=instructions, lifespan=functools.partial(_lifespan, opts)
    )

    def _scope(ctx: Context, task_id: str) -> ServerContext:
        """Reject readonly mode and cross-task reports (MCP-SRV-03, MCP-SEC-01/03)."""
        if opts.readonly:
            raise ToolError("report tools are disabled in read-only mode")
        server_ctx = get_context(ctx)
        bound = server_ctx.bound_task_id
        if bound is not None and task_id != bound:
            raise ToolError(f"task {task_id!r} is outside the bound task {bound!r}")
        return server_ctx

    @mcp.tool()
    async def report_intake_decisions(
        task_id: str, understanding: str, decisions: list[dict[str, Any]], ctx: Context
    ) -> dict[str, Any]:
        """Report the restated understanding and the decisions to pin during intake."""
        sc = _scope(ctx, task_id)
        task = sc.client.record_intake_decisions(
            task_id, understanding=understanding, decisions=decisions
        )
        return {"task_id": task.id, "decisions_recorded": len(task.decisions)}

    @mcp.tool()
    async def report_needs_you(
        task_id: str, reason: str, question: str, ctx: Context, context: str = ""
    ) -> dict[str, Any]:
        """Emit one structured mid-run question and block until the human answers."""
        sc = _scope(ctx, task_id)
        answer = await sc.client.record_needs_you(
            task_id, reason=reason, question=question, context=context
        )
        return {"task_id": task_id, "answer": answer}

    @mcp.tool()
    async def report_smoke_tests(
        task_id: str, tests: list[SmokeReport], ctx: Context
    ) -> dict[str, Any]:
        """Report the behaviours a human should verify, each referencing its service."""
        sc = _scope(ctx, task_id)
        task = sc.client.record_smoke_tests(task_id, tests=[t.model_dump() for t in tests])
        return {"task_id": task.id, "smoke_tests_recorded": len(task.smoke_tests)}

    @mcp.tool()
    async def report_drift(
        task_id: str, message: str, ctx: Context, location: str | None = None
    ) -> dict[str, Any]:
        """Report a self-identified scope or decision violation."""
        sc = _scope(ctx, task_id)
        task = sc.client.record_drift(task_id, message=message, location=location)
        return {"task_id": task.id, "drift_concerns": len(task.drift_concerns)}

    @mcp.tool()
    async def report_findings(
        task_id: str, findings: list[FindingReport], ctx: Context
    ) -> dict[str, Any]:
        """Report adversarial-validator findings (lever 2). Each message must state a
        concrete failure path — no speculative findings. The human adjudicates each."""
        sc = _scope(ctx, task_id)
        task = sc.client.get_task(task_id)
        before = len(task.findings) if task is not None else 0
        for f in findings:
            task = sc.client.add_finding(
                task_id,
                severity=f.severity,
                location=f.location,
                message=f.message,
                source="ai-review",
                confidence=f.confidence,
                status=f.status,
            )
        return {"task_id": task_id, "findings_recorded": len(findings), "findings_before": before}

    @mcp.tool()
    async def report_comprehension_prompts(
        task_id: str, prompts: list[ComprehensionPromptReport], ctx: Context
    ) -> dict[str, Any]:
        """Report diff-specific comprehension questions the human must answer (lever 2)."""
        sc = _scope(ctx, task_id)
        task = sc.client.get_task(task_id)
        before = len(task.comprehension_prompts) if task is not None else 0
        task = sc.client.record_comprehension_prompts(
            task_id, prompts=[p.model_dump() for p in prompts]
        )
        return {
            "task_id": task_id,
            "prompts_recorded": len(task.comprehension_prompts),
            "prompts_before": before,
        }

    @mcp.tool()
    async def report_done(task_id: str, ctx: Context) -> dict[str, Any]:
        """Hint that the agent considers implementation complete."""
        sc = _scope(ctx, task_id)
        task = sc.client.record_done(task_id)
        return {"task_id": task.id, "done_reported": task.done_reported}

    _deref_tool_schemas(mcp)
    logger.info("MCP server created with report tools")
    return mcp


async def serve(opts: ServerOptions) -> None:
    """Create and run the kagan MCP server over STDIO transport."""
    mcp = create_server(opts)
    logger.info("MCP server starting on STDIO")
    await mcp.run_stdio_async()
