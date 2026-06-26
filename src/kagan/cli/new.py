"""`kagan new <title>` — create a task and run intake up front (TUI-INTAKE-01/02).

The created task reaches INTAKE with the agent's plan-only intake already run,
so the human opens the Intake screen to decisions, not a blank task. ``--agent``
and ``--scope`` mirror the interactive picker so a non-interactive create can set
the same fields configure_task sets there.
"""

import click

from kagan.cli._bootstrap import run_async


@click.command(name="new", help="Create a task and run intake (plan-only) on it.")
@click.argument("title")
@click.option(
    "--agent",
    "agent_cli",
    default=None,
    help="Coding agent CLI (must be installed). Omit to drive manually.",
)
@click.option("--scope", "scope", multiple=True, help="Path glob in scope (repeatable).")
def new(title: str, agent_cli: str | None, scope: tuple[str, ...]) -> None:
    from kagan.core import Harness, default_data_dir, find_repo_root

    repo_root = find_repo_root()
    if repo_root is None:
        raise click.ClickException("not inside a Kagan repo (no .kagan/repo.yaml found)")

    # one shared resolver => `new` writes the same ledger the TUI reads.
    core = Harness(data_dir=default_data_dir(repo_root), repo_root=repo_root)
    try:
        if agent_cli is not None:
            # Validate against installed CLIs (not a static Choice): the valid set is
            # whatever is on PATH, same as the interactive picker.
            available = core.available_clis()
            if agent_cli not in available:
                installed = ", ".join(available) or "none"
                raise click.BadParameter(
                    f"agent {agent_cli!r} not available; installed: {installed}",
                    param_hint="--agent",
                )
        scope_list = list(scope) or None
        task = core.create_task(title)
        # MUST configure before intake: run_intake classifies risk and plans from the
        # task's scope/agent, so setting them after would compute against empty scope.
        if agent_cli is not None or scope_list is not None:
            core.configure_task(task.id, agent_cli=agent_cli, scope=scope_list)
        run_async(core.run_intake(task.id))  # blocks: task must reach INTAKE intake-done
        click.echo(task.id)
    finally:
        core.close()
