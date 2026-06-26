"""Hidden detached per-task runner — keeps the interactive session stateless.

`kagan _run <id>` is spawned detached (NOT a user entrypoint, DESIGN 3.5). It
runs the agent to exit, harvests the diff, runs the validator + gate, lands the
task in REVIEW on the ledger, and fires ONE OS notification. The interactive
session is a pure viewer/actor over the ledger; the doing happens here.

This wires the agent-run + harvest + validator + gate on Harness: ``start_task``
launches the agent, ``_watch_agent`` harvests on exit, ``_harvest`` then runs the
lever-2 validator (RUNNING -> VALIDATING) and the gate (VALIDATING -> REVIEW). So
``await_agent`` returning means the task has already settled in REVIEW with the
validator's findings merged.
"""

from pathlib import Path

import click

from kagan.cli._bootstrap import run_async


@click.command(
    name="_run",
    hidden=True,
    help="Detached per-task runner (internal — spawned by the session, not a user command).",
)
@click.argument("task_id")
@click.option(
    "--data-dir", "data_dir", default=None, help="Ledger root (passed by the spawning session)."
)
def _run(task_id: str, data_dir: str | None) -> None:
    from kagan.core import git

    repo_root = git.repo_root(Path.cwd())
    explicit = Path(data_dir).expanduser().resolve(strict=False) if data_dir else None
    run_async(_run_task(task_id, data_dir=explicit, repo_root=repo_root))


async def _run_task(task_id: str, *, data_dir: Path | None, repo_root: Path | None) -> None:
    from kagan.core import Harness, NotificationEvent, default_data_dir

    resolved = data_dir if data_dir is not None else default_data_dir(repo_root)
    core = Harness(data_dir=resolved, repo_root=repo_root)
    try:
        # start_task launches the agent; the background watcher harvests the diff on
        # process exit, runs the lever-2 validator (RUNNING -> VALIDATING, merges
        # ai-review findings), then the gate (mirror checks + rubric) into REVIEW.
        await core.start_task(task_id)
        await core.await_agent(task_id)

        # DEFER (Phase 3 / lever 4): per-finding independent verify sub-agents, the
        # variant sweep, the risk-routed confidence gate, and validator-generated
        # comprehension probes (lever 1 upgrade) are NOT built — Phase 2 is the
        # single validator stage only (DESIGN 3.8 / lever 2).

        # One OS notification once the task has settled in REVIEW (DESIGN 3.5).
        task = core.get_task(task_id)
        if task is not None and task.state.value == "review":
            await core.notify(NotificationEvent.REVIEW, task_id)
    finally:
        await core.aclose()


__all__ = ["_run"]
