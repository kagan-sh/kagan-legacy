"""Output formatting helpers for the kagan doctor command."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click
from rich import box
from rich.console import Console, Group
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from kagan.cli.doctor import DoctorCheck


_STATUS_STYLES = {
    "pass": "green",
    "warn": "yellow",
    "fail": "red",
}
_BACKEND_CHECK_PREFIX = "backend: "


def emit_tldr(checks: list[DoctorCheck]) -> None:
    total = len(checks)
    passed = sum(1 for c in checks if c.status == "pass")
    warned = sum(1 for c in checks if c.status == "warn")
    failed = sum(1 for c in checks if c.status == "fail")
    click.echo(f"doctor: {total} checks | PASS {passed} | WARN {warned} | FAIL {failed}")


def emit_short(checks: list[DoctorCheck]) -> None:
    Console(highlight=False).print(render_short(checks))


def emit_technical(checks: list[DoctorCheck]) -> None:
    for check in checks:
        label = check.status.upper()
        click.echo(f"{label:<4} {check.name}")
        click.echo(f"  detail: {check.message}")
        if check.fix_hint:
            click.echo(f"  quick fix: {check.fix_hint}")
        click.echo(f"  verify: {check.verify_hint}")


def render_short(checks: list[DoctorCheck]) -> Group:
    """Render the default doctor report as a compact Rich component."""
    return Group(
        _summary_panel(checks),
        _required_table(checks),
        _backend_panel(checks),
        _action_table(checks),
    )


def _summary_panel(checks: list[DoctorCheck]) -> Panel:
    total = len(checks)
    passed = sum(1 for c in checks if c.status == "pass")
    warned = sum(1 for c in checks if c.status == "warn")
    failed = sum(1 for c in checks if c.status == "fail")

    if failed:
        state = Text("Needs attention", style="bold red")
        border = "red"
    elif warned:
        state = Text("Usable with warnings", style="bold yellow")
        border = "yellow"
    else:
        state = Text("Ready", style="bold green")
        border = "green"

    body = Text.assemble(
        state,
        "\n",
        ("PASS ", "bold green"),
        (str(passed), "green"),
        "  ",
        ("WARN ", "bold yellow"),
        (str(warned), "yellow"),
        "  ",
        ("FAIL ", "bold red"),
        (str(failed), "red"),
        ("  /  ", "dim"),
        (f"{total} checks", "dim"),
    )
    return Panel(body, title="Kagan Doctor", border_style=border, box=box.ROUNDED)


def _required_table(checks: list[DoctorCheck]) -> Table:
    rows = [
        check
        for check in checks
        if check.category != "backend" and not check.name.startswith(_BACKEND_CHECK_PREFIX)
    ]
    table = Table(
        title="Required environment",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold",
        pad_edge=False,
    )
    table.add_column("Status", no_wrap=True)
    table.add_column("Check", no_wrap=True)
    table.add_column("Result")

    for check in rows:
        table.add_row(
            _status_label(check.status),
            escape(check.name),
            escape(check.message),
        )
    return table


def _backend_panel(checks: list[DoctorCheck]) -> Panel:
    summary = next(
        (c for c in checks if c.category == "backend" and c.name == "agent backends"),
        None,
    )
    backend_rows = [
        c for c in checks if c.category == "backend" and c.name.startswith(_BACKEND_CHECK_PREFIX)
    ]
    installed = [_backend_display_name(c) for c in backend_rows if c.status == "pass"]
    missing = [_backend_display_name(c) for c in backend_rows if c.status != "pass"]

    lines: list[Text] = []
    if summary is not None:
        lines.append(
            Text.assemble(
                _status_label(summary.status),
                " ",
                (summary.message, _STATUS_STYLES.get(summary.status, "")),
            )
        )
    if installed:
        lines.append(Text.assemble(("Installed: ", "bold green"), ", ".join(installed)))
    if missing:
        lines.append(Text.assemble(("Optional missing: ", "bold yellow"), ", ".join(missing)))
    if not lines:
        lines.append(Text("No backend checks returned.", style="dim"))

    return Panel(Group(*lines), title="Agent backends", border_style="dim", box=box.ROUNDED)


def _action_table(checks: list[DoctorCheck]) -> Table:
    actionable = [
        c
        for c in checks
        if c.status in {"warn", "fail"}
        and c.fix_hint
        and not (c.category == "backend" and c.name.startswith(_BACKEND_CHECK_PREFIX))
    ]

    table = Table(
        title="Actions",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold",
        pad_edge=False,
    )
    table.add_column("Check", no_wrap=True)
    table.add_column("Fix")

    if not actionable:
        table.add_row("None", "No required fixes.")
        return table

    for check in actionable:
        table.add_row(escape(check.name), escape(check.fix_hint))
    return table


def _status_label(status: str) -> Text:
    return Text(status.upper(), style=f"bold {_STATUS_STYLES.get(status, '')}".strip())


def _backend_display_name(check: DoctorCheck) -> str:
    return check.name.removeprefix(_BACKEND_CHECK_PREFIX).strip()
