"""Output formatting helpers for the kagan doctor command."""

from typing import TYPE_CHECKING

import click

from kagan.format._console import print_themed
from kagan.format.doctor import (
    format_doctor_technical,
    format_doctor_tldr,
    render_preflight,
)

if TYPE_CHECKING:
    from kagan.core.doctor_checks import DoctorCheck


def emit_tldr(checks: list[DoctorCheck]) -> None:
    click.echo(format_doctor_tldr(checks))


def emit_short(checks: list[DoctorCheck]) -> None:
    # DESIGN §5 doctor: the default form reuses the calm preflight — ONE visual
    # language for the same data (the panel/table form is `--verbosity technical`).
    print_themed(render_preflight(checks))


def emit_technical(checks: list[DoctorCheck]) -> None:
    click.echo(format_doctor_technical(checks))


__all__ = [
    "emit_short",
    "emit_technical",
    "emit_tldr",
]
