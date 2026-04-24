import json
from dataclasses import dataclass, field

import click
from loguru import logger

from kagan.cli._bootstrap import make_client, run_async
from kagan.cli._doctor_output import emit_short, emit_technical, emit_tldr
from kagan.core import PreflightCheckResult
from kagan.core._analytics import emit_telemetry
from kagan.core._db import create_db_engine, default_db_path
from kagan.core._environment_checks import (
    _VERIFY_HINTS,
    _derive_category,
    collect_environment_checks,
    resolve_backend_guidance,
    resolve_doctor_backend_name,
    verify_hint_for,
)
from kagan.core.enums import SessionEventType
from kagan.core.errors import KaganError
from kagan.core.plugins import PluginManager


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    message: str
    fix_hint: str
    verify_hint: str
    category: str = field(default="core")


def _verify_hint(name: str) -> str:
    return _VERIFY_HINTS.get(name, "ls")


def _backend_verify_hint(backend_name: str) -> str:
    """Return a verify command for a specific backend name."""
    return verify_hint_for("agent backend", backend_name)


def _map_preflight_check(check: PreflightCheckResult, default_backend: str) -> DoctorCheck:
    """Convert a PreflightCheckResult into a DoctorCheck.

    Handles both legacy single-backend results (name="agent_backend") and
    new multi-backend results (name="agent_backend:{backend_name}").
    Multi-backend results should go through _collapse_backend_checks instead;
    this path handles legacy and non-backend results.
    """
    raw_name = check.name

    # Multi-backend result: name is "agent_backend:{backend_name}"
    if raw_name.startswith("agent_backend:"):
        backend_name = raw_name[len("agent_backend:") :]
        is_default = backend_name == default_backend
        display_name = (
            f"agent backend: {backend_name} (default)"
            if is_default
            else f"agent backend: {backend_name}"
        )
        fix_hint = check.fix_hint
        if is_default and check.status != "pass":
            guidance = resolve_backend_guidance(backend_name)
            if guidance:
                fix_hint = f"{fix_hint} {guidance}".strip() if fix_hint else guidance
        return DoctorCheck(
            name=display_name,
            status=str(check.status),
            message=check.message,
            fix_hint=fix_hint,
            verify_hint=_backend_verify_hint(backend_name),
            category="backend",
        )

    # Legacy single-backend result: name is "agent_backend" (underscore)
    name = raw_name.replace("_", " ")
    message = check.message
    fix_hint = check.fix_hint
    v_hint = verify_hint_for(name, default_backend if name == "agent backend" else None)
    if name == "agent backend":
        message = f"Default agent backend '{default_backend}': {check.message}"
        guidance = resolve_backend_guidance(default_backend)
        if guidance and check.status != "pass":
            fix_hint = f"{check.fix_hint} {guidance}".strip() if check.fix_hint else guidance
    return DoctorCheck(
        name=name,
        status=str(check.status),
        message=message,
        fix_hint=fix_hint,
        verify_hint=v_hint,
        category=_derive_category(name),
    )


def _collapse_backend_checks(
    preflight_results: list[PreflightCheckResult],
    default_backend: str,
) -> list[DoctorCheck]:
    """Collapse multi-backend PreflightCheckResults into DoctorChecks for display.

    Produces:
    - Non-backend checks mapped individually (git, tmux, db, etc.).
    - One summary DoctorCheck named "agent backends" (category="backend") with
      the default backend's severity — FAIL triggers DoctorModal zero-ready state.
    - One DoctorCheck per backend (category="backend") for expandable detail.

    The summary row is authoritative for DoctorModal's blocking condition:
    ``any(check.status == "fail")`` is True when the default backend is missing.
    """
    backend_results = [r for r in preflight_results if r.name.startswith("agent_backend:")]
    non_backend = [r for r in preflight_results if not r.name.startswith("agent_backend:")]

    other_checks = [_map_preflight_check(r, default_backend) for r in non_backend]

    if not backend_results:
        return other_checks

    # Derive summary status from the default backend result
    default_result = next(
        (r for r in backend_results if r.name == f"agent_backend:{default_backend}"),
        backend_results[0],
    )

    installed_count = sum(1 for r in backend_results if str(r.status) == "pass")
    total_count = len(backend_results)

    summary_status = str(default_result.status)
    if summary_status == "pass":
        summary_msg = (
            f"Default backend '{default_backend}' ready"
            f" — {installed_count}/{total_count} backends installed"
        )
    else:
        summary_msg = (
            f"Default backend '{default_backend}' not found"
            f" — {installed_count}/{total_count} backends installed"
        )

    summary_hint = default_result.fix_hint
    if summary_status != "pass":
        guidance = resolve_backend_guidance(default_backend)
        if guidance:
            summary_hint = f"{summary_hint} {guidance}".strip() if summary_hint else guidance

    summary_check = DoctorCheck(
        name="agent backends",
        status=summary_status,
        message=summary_msg,
        fix_hint=summary_hint,
        verify_hint=_backend_verify_hint(default_backend),
        category="backend",
    )

    # Per-backend detail rows (all backends, shown for detail / JSON output)
    detail_checks: list[DoctorCheck] = []
    for result in backend_results:
        backend_name = result.name[len("agent_backend:") :]
        is_default = backend_name == default_backend
        display = f"backend: {backend_name}" + (" (default)" if is_default else "")
        detail_fix = result.fix_hint
        if is_default and str(result.status) != "pass":
            guidance = resolve_backend_guidance(backend_name)
            if guidance:
                detail_fix = f"{detail_fix} {guidance}".strip() if detail_fix else guidance
        detail_checks.append(
            DoctorCheck(
                name=display,
                status=str(result.status),
                message=result.message,
                fix_hint=detail_fix,
                verify_hint=_backend_verify_hint(backend_name),
                category="backend",
            )
        )

    return [*other_checks, summary_check, *detail_checks]


async def _load_and_collect_plugin_checks(manager: PluginManager) -> list[PreflightCheckResult]:
    await manager.load()
    return manager.preflight()


def _collect_doctor_checks() -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    client = make_client()
    try:
        default_backend = run_async(resolve_doctor_backend_name(client))
        preflight = run_async(client.preflight(agent_backend=default_backend))

        # Detect whether we have new multi-backend results
        backend_results = [r for r in preflight if r.name.startswith("agent_backend:")]
        if backend_results:
            # New multi-backend path: collapse into summary + detail rows
            checks.extend(_collapse_backend_checks(preflight, default_backend))
        else:
            # Legacy path: map each result individually
            for check in preflight:
                checks.append(_map_preflight_check(check, default_backend))

        for env_result in collect_environment_checks():
            checks.append(
                DoctorCheck(
                    name=env_result["name"],
                    status=env_result["status"],
                    message=env_result["message"],
                    fix_hint=env_result["fix_hint"],
                    verify_hint=env_result["verify_hint"],
                    category=env_result["category"],
                )
            )

        try:
            plugin_manager = PluginManager(client)
            plugin_checks = run_async(_load_and_collect_plugin_checks(plugin_manager))
            for pc in plugin_checks:
                name = pc.name.replace("_", " ")
                checks.append(
                    DoctorCheck(
                        name=name,
                        status=str(pc.status),
                        message=pc.message,
                        fix_hint=pc.fix_hint,
                        verify_hint=_verify_hint(name),
                        category="plugin",
                    )
                )
        except (ImportError, KaganError, RuntimeError):
            logger.opt(exception=True).debug("Plugin preflight collection failed")
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    return checks


def _emit_json(checks: list[DoctorCheck]) -> None:
    """Emit checks as a JSON array to stdout (one object per check, six fields each)."""
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


def _emit_doctor_warned_telemetry(checks: list[DoctorCheck]) -> None:
    """Emit a DOCTOR_WARNED telemetry event when any WARN or FAIL check is present."""
    problem_checks = [c for c in checks if c.status in {"warn", "fail"}]
    if not problem_checks:
        return

    warn_count = sum(1 for c in problem_checks if c.status == "warn")
    fail_count = sum(1 for c in problem_checks if c.status == "fail")
    failing_check_names = [c.name for c in problem_checks]

    try:
        engine = create_db_engine(default_db_path())
        run_async(
            emit_telemetry(
                engine,
                SessionEventType.DOCTOR_WARNED,
                {
                    "failing_check_names": failing_check_names,
                    "warn_count": warn_count,
                    "fail_count": fail_count,
                },
            )
        )
        logger.debug("Emitted doctor_warned telemetry: warn={} fail={}", warn_count, fail_count)
    except Exception:
        # Telemetry is best-effort; never block the CLI
        logger.opt(exception=True).debug("Failed to emit doctor_warned telemetry")


@click.command(
    name="doctor",
    epilog=(
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

    has_failures = any(check.status == "fail" for check in checks)
    if has_failures and not output_json:
        from kagan.core._logging import default_log_path

        click.echo(f"\nLog file: {default_log_path()}")

    _emit_doctor_warned_telemetry(checks)

    click.get_current_context().exit(1 if has_failures else 0)


def run_doctor_checks() -> list[DoctorCheck]:
    return _collect_doctor_checks()


def run_doctor_check_for_backend(backend_name: str) -> DoctorCheck | None:
    """Targeted single-backend preflight — one shutil.which, no full survey.

    Does NOT call check_agent_backends() or list_available_backends().
    Exactly one shutil.which() call fires, for the named backend only.
    No environment, plugin, or IDE checks are invoked.

    FAIL (not WARN) is deliberate here: this is called after an install
    attempt. If the binary is still missing, that is a hard failure for
    this recheck call path, distinct from the initial survey severity rules.

    Args:
        backend_name: The canonical backend name (e.g. ``"claude-code"``).

    Returns:
        A :class:`DoctorCheck` for that backend, or ``None`` if the backend
        name is not registered in AGENT_BACKENDS.
    """
    import shutil

    from kagan.core._agent import AGENT_BACKENDS

    spec = AGENT_BACKENDS.get(backend_name)
    if spec is None:
        return None

    executable = spec["executable"]
    installed = shutil.which(executable) is not None
    status = "pass" if installed else "fail"
    if installed:
        message = f"Agent backend '{backend_name}' found (executable: {executable})"
        fix_hint = ""
    else:
        message = f"Agent backend '{backend_name}' not found (executable: {executable})"
        fix_hint = f"Install {backend_name} and ensure '{executable}' is on PATH"
        guidance = resolve_backend_guidance(backend_name)
        if guidance:
            fix_hint = f"{fix_hint} {guidance}".strip()

    return DoctorCheck(
        name=f"agent backend: {backend_name}",
        status=status,
        message=message,
        fix_hint=fix_hint,
        verify_hint=_backend_verify_hint(backend_name),
        category="backend",
    )


def render_doctor_report(
    checks: list[DoctorCheck],
    *,
    title: str = "Kagan Doctor",
    verbosity: str = "short",
) -> None:
    click.echo()
    click.secho(title, bold=True)
    click.echo()
    if verbosity == "tldr":
        emit_tldr(checks)
    elif verbosity == "technical":
        emit_technical(checks)
    else:
        emit_short(checks)

    if any(c.status == "fail" for c in checks):
        from kagan.core._logging import default_log_path

        click.echo(f"\nLog file: {default_log_path()}")


def doctor_has_failures(checks: list[DoctorCheck]) -> bool:
    return any(check.status == "fail" for check in checks)
