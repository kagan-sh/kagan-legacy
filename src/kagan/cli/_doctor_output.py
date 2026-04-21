"""Output formatting helpers for the kagan doctor command.

Each ``_emit_*`` function prints a human-readable representation of a list
of DoctorCheck results to stdout via ``click.echo``.  They are kept here so
``cli/doctor.py`` stays below the 250-line budget.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from kagan.cli.doctor import DoctorCheck


def emit_tldr(checks: list[DoctorCheck]) -> None:
    total = len(checks)
    passed = sum(1 for c in checks if c.status == "pass")
    warned = sum(1 for c in checks if c.status == "warn")
    failed = sum(1 for c in checks if c.status == "fail")
    click.echo(f"doctor: {total} checks | PASS {passed} | WARN {warned} | FAIL {failed}")


def emit_short(checks: list[DoctorCheck]) -> None:
    for check in checks:
        label = check.status.upper()
        click.echo(f"{label:<4} {check.name}: {check.message}")
        if check.status in {"warn", "fail"} and check.fix_hint:
            click.echo(f"  quick fix: {check.fix_hint}")


def emit_technical(checks: list[DoctorCheck]) -> None:
    for check in checks:
        label = check.status.upper()
        click.echo(f"{label:<4} {check.name}")
        click.echo(f"  detail: {check.message}")
        if check.fix_hint:
            click.echo(f"  quick fix: {check.fix_hint}")
        click.echo(f"  verify: {check.verify_hint}")
