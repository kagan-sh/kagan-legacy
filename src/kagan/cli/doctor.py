import json

import click
from loguru import logger

from kagan.cli.doctor_emit import emit_short, emit_technical, emit_tldr
from kagan.core import default_log_path
from kagan.core.doctor_checks import (
    DoctorCheck,
    doctor_has_failures,
    run_doctor_checks,
)


def _collect_doctor_checks() -> list[DoctorCheck]:
    # Run and return all doctor checks.
    return run_doctor_checks()


def _emit_json(checks: list[DoctorCheck]) -> None:
    data = [
        {
            "name": c.name,
            "status": c.status,
            "message": c.message,
            "fix_hint": c.fix_hint,
            "verify_hint": c.verify_hint,
            "category": c.category,
        }
        for c in checks
    ]
    click.echo(json.dumps(data))


@click.command(
    name="doctor",
    short_help="Check system health (git, python, agents, repo config).",
    epilog=(
        "\b\n"
        "Examples:\n"
        "  kagan doctor                      Quick health check\n"
        "  kagan doctor --verbosity tldr     One-line summary\n"
        "  kagan doctor --verbosity technical Full diagnostic output\n"
        "  kagan doctor --json               Machine-readable JSON output"
    ),
)
@click.option(
    "--verbosity",
    type=click.Choice(["tldr", "short", "technical"], case_sensitive=False),
    default="short",
    show_default=True,
    help="How much detail to print: tldr (one line), short, or technical.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Emit results as a JSON array to stdout instead of human-readable output.",
)
def doctor(verbosity: str, output_json: bool) -> None:
    checks = _collect_doctor_checks()
    logger.debug("Doctor checks collected: {}", len(checks))

    if output_json:
        _emit_json(checks)
    elif verbosity == "tldr":
        emit_tldr(checks)
    elif verbosity == "technical":
        emit_technical(checks)
    else:
        emit_short(checks)

    if doctor_has_failures(checks) and not output_json:
        click.echo(f"\nLog file: {default_log_path()}")

    click.get_current_context().exit(1 if doctor_has_failures(checks) else 0)


__all__ = [
    "DoctorCheck",
    "doctor",
    "doctor_has_failures",
    "run_doctor_checks",
]
