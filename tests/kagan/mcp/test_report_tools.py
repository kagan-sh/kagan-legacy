"""MCP report-tool contract tests (MCP-SRV/INTAKE/SMOKE/DRIFT/DONE/SEC).

call_tool is driven through an in-memory client session so the FastMCP lifespan
runs and each result carries `isError` (the high-level `FastMCP.call_tool`
returns raw content and raises on error, so it cannot prove the error path).
"""

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from kagan.core import Harness
from kagan.mcp.server import ServerOptions, create_server


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "kagan.db"


@pytest.mark.mcp
async def test_report_intake_decisions_tool(data_dir):
    # MCP-INTAKE-02: the tool routes understanding + decisions to the ledger.
    server = create_server(ServerOptions(data_dir=str(data_dir)))
    task = Harness(data_dir=data_dir).create_task("Add feature")
    async with connect(server) as client:
        result = await client.call_tool(
            "report_intake_decisions",
            {
                "task_id": task.id,
                "understanding": "Add dark mode",
                "decisions": [{"question": "Which file?", "severity": "blocking"}],
            },
        )
    assert result.isError is False
    assert Harness(data_dir=data_dir).get_task(task.id).understanding == "Add dark mode"


@pytest.mark.mcp
async def test_report_smoke_tests_tool(data_dir):
    # MCP-SMOKE-01/02: behaviours + service reference reach the ledger.
    server = create_server(ServerOptions(data_dir=str(data_dir)))
    task = Harness(data_dir=data_dir).create_task("Add feature")
    async with connect(server) as client:
        result = await client.call_tool(
            "report_smoke_tests",
            {"task_id": task.id, "tests": [{"behaviour": "Toggle dark mode", "service": "web"}]},
        )
    assert result.isError is False
    smokes = Harness(data_dir=data_dir).get_task(task.id).smoke_tests
    assert smokes[0].service == "web"


@pytest.mark.mcp
async def test_report_smoke_tests_schema_is_deref_inlined(data_dir):
    # MCP-SRV (P7): a nested Pydantic param emits $ref/$defs; the registered schema
    # must be flattened inline so strict MCP clients accept it.
    server = create_server(ServerOptions(data_dir=str(data_dir)))
    tools = {t.name: t for t in await server.list_tools()}
    schema = tools["report_smoke_tests"].inputSchema
    assert "$defs" not in schema
    items = schema["properties"]["tests"]["items"]
    assert "$ref" not in items
    assert set(items["properties"]) >= {"behaviour", "service"}


@pytest.mark.mcp
async def test_report_drift_tool(data_dir):
    # MCP-DRIFT-02: a self-reported concern appends to the task.
    server = create_server(ServerOptions(data_dir=str(data_dir)))
    task = Harness(data_dir=data_dir).create_task("Add feature")
    async with connect(server) as client:
        result = await client.call_tool(
            "report_drift", {"task_id": task.id, "message": "Edited api.py"}
        )
    assert result.isError is False
    assert len(Harness(data_dir=data_dir).get_task(task.id).drift_concerns) == 1


@pytest.mark.mcp
async def test_report_done_tool(data_dir):
    # MCP-DONE-01: the completion hint flips done_reported.
    server = create_server(ServerOptions(data_dir=str(data_dir)))
    task = Harness(data_dir=data_dir).create_task("Add feature")
    async with connect(server) as client:
        result = await client.call_tool("report_done", {"task_id": task.id})
    assert result.isError is False
    assert Harness(data_dir=data_dir).get_task(task.id).done_reported is True


@pytest.mark.mcp
async def test_report_findings_tool_lands_ai_review_source(data_dir):
    # Lever 2: the validator's findings reach the ledger through the same single-writer
    # path, source-stamped ai-review with confidence/status, NOT auto-adjudicated
    # (verdict stays None so the human still decides).
    server = create_server(ServerOptions(data_dir=str(data_dir)))
    task = Harness(data_dir=data_dir).create_task("Add feature")
    async with connect(server) as client:
        result = await client.call_tool(
            "report_findings",
            {
                "task_id": task.id,
                "findings": [
                    {
                        "severity": "blocking",
                        "location": "src/eval.rs:80",
                        "message": "'2+3*4' evaluates to 20, not 14 — precedence ignored",
                        "confidence": 9,
                        "status": "VERIFIED",
                    }
                ],
            },
        )
    assert result.isError is False
    findings = Harness(data_dir=data_dir).get_task(task.id).findings
    assert len(findings) == 1
    assert findings[0].source == "ai-review"
    assert findings[0].confidence == 9
    assert findings[0].status == "VERIFIED"
    assert findings[0].verdict is None  # the human still adjudicates it


@pytest.mark.mcp
async def test_report_comprehension_prompts_tool(data_dir):
    server = create_server(ServerOptions(data_dir=str(data_dir)))
    task = Harness(data_dir=data_dir).create_task("Billing retry")
    prompts = [
        {"key": "postcondition", "question": "How does billing retry after this diff?"},
        {"key": "what_breaks", "question": "What race could still lose a charge?"},
    ]
    async with connect(server) as client:
        result = await client.call_tool(
            "report_comprehension_prompts",
            {"task_id": task.id, "prompts": prompts},
        )
    assert result.isError is False
    stored = Harness(data_dir=data_dir).get_task(task.id).comprehension_prompts
    assert stored == [
        ("postcondition", "How does billing retry after this diff?"),
        ("what_breaks", "What race could still lose a charge?"),
    ]


@pytest.mark.mcp
async def test_report_comprehension_prompts_disabled_in_readonly(data_dir):
    server = create_server(ServerOptions(data_dir=str(data_dir), readonly=True))
    task = Harness(data_dir=data_dir).create_task("Billing retry")
    async with connect(server) as client:
        result = await client.call_tool(
            "report_comprehension_prompts",
            {
                "task_id": task.id,
                "prompts": [{"key": "postcondition", "question": "q?"}],
            },
        )
    assert result.isError is True
    assert not Harness(data_dir=data_dir).get_task(task.id).comprehension_prompts


@pytest.mark.mcp
async def test_report_comprehension_prompts_rejects_cross_task_when_bound(data_dir):
    server = create_server(ServerOptions(data_dir=str(data_dir), task_id="task-bound"))
    async with connect(server) as client:
        result = await client.call_tool(
            "report_comprehension_prompts",
            {
                "task_id": "other",
                "prompts": [{"key": "postcondition", "question": "q?"}],
            },
        )
    assert result.isError is True


@pytest.mark.mcp
async def test_report_findings_disabled_in_readonly(data_dir):
    # MCP-SEC: read-only mode rejects the validator's mutating report too.
    server = create_server(ServerOptions(data_dir=str(data_dir), readonly=True))
    task = Harness(data_dir=data_dir).create_task("Add feature")
    async with connect(server) as client:
        result = await client.call_tool(
            "report_findings",
            {
                "task_id": task.id,
                "findings": [{"severity": "blocking", "location": "x", "message": "y"}],
            },
        )
    assert result.isError is True
    assert not Harness(data_dir=data_dir).get_task(task.id).findings


@pytest.mark.mcp
async def test_report_findings_rejects_cross_task_when_bound(data_dir):
    # MCP-SEC-01/03: a task-bound validator server refuses findings aimed elsewhere.
    server = create_server(ServerOptions(data_dir=str(data_dir), task_id="task-bound"))
    async with connect(server) as client:
        result = await client.call_tool(
            "report_findings",
            {
                "task_id": "other",
                "findings": [{"severity": "blocking", "location": "x", "message": "y"}],
            },
        )
    assert result.isError is True


@pytest.mark.mcp
async def test_report_bad_args_returns_error_not_raises(data_dir):
    # P7: a ValidationError becomes an error result, never an exception that
    # kills the agent run.
    server = create_server(ServerOptions(data_dir=str(data_dir)))
    async with connect(server) as client:
        result = await client.call_tool("report_smoke_tests", {"task_id": "t-1"})  # no "tests"
    assert result.isError is True


@pytest.mark.mcp
async def test_report_disabled_in_readonly(data_dir):
    # MCP-SEC: read-only mode rejects every state-mutating report.
    server = create_server(ServerOptions(data_dir=str(data_dir), readonly=True))
    task = Harness(data_dir=data_dir).create_task("Add feature")
    async with connect(server) as client:
        result = await client.call_tool("report_done", {"task_id": task.id})
    assert result.isError is True


@pytest.mark.mcp
async def test_report_rejects_cross_task_when_bound(data_dir):
    # MCP-SEC-01/03: a task-bound server refuses reports aimed at another task.
    server = create_server(ServerOptions(data_dir=str(data_dir), task_id="task-bound"))
    async with connect(server) as client:
        result = await client.call_tool("report_done", {"task_id": "other-task"})
    assert result.isError is True
