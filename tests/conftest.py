"""Pytest fixtures for Kagan tests."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from kagan.app import KaganApp
from kagan.database.manager import StateManager

# =============================================================================
# Existing Unit Test Fixtures
# =============================================================================


@pytest.fixture
async def state_manager():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        manager = StateManager(db_path)
        await manager.initialize()
        yield manager
        await manager.close()


@pytest.fixture
def app() -> KaganApp:
    """Create app with in-memory database."""
    return KaganApp(db_path=":memory:")


# =============================================================================
# E2E Test Fixtures
# =============================================================================


@pytest.fixture
async def e2e_project(tmp_path: Path):
    """Create a real project with git repo and kagan config for E2E testing.

    This fixture provides:
    - A real git repository with initial commit
    - A .kagan/config.toml file
    - Paths to DB and config for KaganApp initialization
    """
    project = tmp_path / "test_project"
    project.mkdir()

    # Initialize real git repo
    proc = await asyncio.create_subprocess_exec(
        "git",
        "init",
        "-b",
        "main",
        cwd=project,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    # Configure git user
    for cmd in [
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test User"],
        ["config", "commit.gpgsign", "false"],
    ]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *cmd,
            cwd=project,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    # Create initial commit
    readme = project / "README.md"
    readme.write_text("# Test Project\n")

    proc = await asyncio.create_subprocess_exec(
        "git",
        "add",
        ".",
        cwd=project,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    proc = await asyncio.create_subprocess_exec(
        "git",
        "commit",
        "-m",
        "Initial commit",
        cwd=project,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    # Create .kagan directory with config
    kagan_dir = project / ".kagan"
    kagan_dir.mkdir()

    config_content = """# Kagan Test Configuration
[general]
auto_start = false
auto_merge = false
default_base_branch = "main"
default_worker_agent = "claude"

[agents.claude]
identity = "claude.ai"
name = "Claude"
short_name = "claude"
run_command."*" = "echo mock-claude"
interactive_command."*" = "echo mock-claude-interactive"
active = true
"""
    (kagan_dir / "config.toml").write_text(config_content)

    return SimpleNamespace(
        root=project,
        db=str(kagan_dir / "state.db"),
        config=str(kagan_dir / "config.toml"),
        kagan_dir=kagan_dir,
    )


@pytest.fixture
def mock_agent_spawn(monkeypatch):
    """Mock ACP agent subprocess spawning.

    This is the ONLY mock we use in E2E tests - everything else is real.
    The mock prevents actual agent CLI processes from starting.
    """
    original_exec = asyncio.create_subprocess_exec

    async def selective_mock(*args, **kwargs):
        # Only mock agent-related commands, allow git commands through
        cmd = args[0] if args else ""
        if cmd in ("git", "tmux"):
            return await original_exec(*args, **kwargs)

        # Mock agent processes
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None
        mock_process.stdout = MagicMock()
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr = MagicMock()
        mock_process.stderr.readline = AsyncMock(return_value=b"")
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        return mock_process

    monkeypatch.setattr("asyncio.create_subprocess_exec", selective_mock)


@pytest.fixture
async def e2e_app(e2e_project):
    """Create a KaganApp configured for E2E testing with real git repo."""
    app = KaganApp(
        db_path=e2e_project.db,
        config_path=e2e_project.config,
        lock_path=None,  # Disable lock for tests
    )
    return app


@pytest.fixture
async def e2e_fresh_project(tmp_path: Path):
    """Create a project directory WITHOUT git initialization.

    This simulates a user running kagan in a completely empty folder,
    which triggers kagan to initialize git itself. This is critical for
    testing that kagan's git initialization creates a valid repo that
    supports worktree creation.
    """
    project = tmp_path / "fresh_project"
    project.mkdir()

    # NO git init - kagan should do this itself
    # Just create .kagan config so it skips welcome screen
    kagan_dir = project / ".kagan"
    kagan_dir.mkdir()

    config_content = """# Kagan Test Configuration
[general]
auto_start = false
auto_merge = false
default_base_branch = "main"
default_worker_agent = "claude"

[agents.claude]
identity = "claude.ai"
name = "Claude"
short_name = "claude"
run_command."*" = "echo mock-claude"
interactive_command."*" = "echo mock-claude-interactive"
active = true
"""
    (kagan_dir / "config.toml").write_text(config_content)

    return SimpleNamespace(
        root=project,
        db=str(kagan_dir / "state.db"),
        config=str(kagan_dir / "config.toml"),
        kagan_dir=kagan_dir,
    )


@pytest.fixture
async def e2e_app_fresh(e2e_fresh_project):
    """Create a KaganApp for a fresh project without git.

    Kagan will initialize git when it detects no repo exists.
    """
    app = KaganApp(
        db_path=e2e_fresh_project.db,
        config_path=e2e_fresh_project.config,
        lock_path=None,
    )
    return app


@pytest.fixture
async def e2e_app_with_tickets(e2e_project):
    """Create a KaganApp with pre-populated tickets for testing.

    Tickets are created via StateManager before the app runs,
    simulating a user who has already been using Kagan.
    """
    from kagan.database.models import TicketCreate, TicketPriority, TicketStatus

    # Initialize state manager and create tickets
    manager = StateManager(e2e_project.db)
    await manager.initialize()

    await manager.create_ticket(
        TicketCreate(
            title="Backlog task",
            description="A task in backlog",
            priority=TicketPriority.LOW,
            status=TicketStatus.BACKLOG,
        )
    )
    await manager.create_ticket(
        TicketCreate(
            title="In progress task",
            description="Currently working",
            priority=TicketPriority.HIGH,
            status=TicketStatus.IN_PROGRESS,
        )
    )
    await manager.create_ticket(
        TicketCreate(
            title="Review task",
            description="Ready for review",
            priority=TicketPriority.MEDIUM,
            status=TicketStatus.REVIEW,
        )
    )

    await manager.close()

    # Create app pointing to same DB
    app = KaganApp(
        db_path=e2e_project.db,
        config_path=e2e_project.config,
        lock_path=None,
    )
    return app


@pytest.fixture
async def e2e_app_with_auto_ticket(e2e_project):
    """Create a KaganApp with an AUTO ticket in IN_PROGRESS for testing.

    This is used to test AUTO ticket movement restrictions.
    """
    from kagan.database.models import TicketCreate, TicketPriority, TicketStatus, TicketType

    manager = StateManager(e2e_project.db)
    await manager.initialize()

    # Create an AUTO ticket in IN_PROGRESS
    await manager.create_ticket(
        TicketCreate(
            title="Auto task in progress",
            description="An AUTO task currently being worked on by agent",
            priority=TicketPriority.HIGH,
            status=TicketStatus.IN_PROGRESS,
            ticket_type=TicketType.AUTO,
        )
    )

    await manager.close()

    app = KaganApp(
        db_path=e2e_project.db,
        config_path=e2e_project.config,
        lock_path=None,
    )
    return app


@pytest.fixture
async def e2e_app_with_done_ticket(e2e_project):
    """Create a KaganApp with a ticket in DONE status for testing.

    This is used to test DONE -> BACKLOG jump behavior.
    """
    from kagan.database.models import TicketCreate, TicketPriority, TicketStatus

    manager = StateManager(e2e_project.db)
    await manager.initialize()

    # Create a DONE ticket
    await manager.create_ticket(
        TicketCreate(
            title="Completed task",
            description="A task that has been completed",
            priority=TicketPriority.MEDIUM,
            status=TicketStatus.DONE,
        )
    )

    await manager.close()

    app = KaganApp(
        db_path=e2e_project.db,
        config_path=e2e_project.config,
        lock_path=None,
    )
    return app
