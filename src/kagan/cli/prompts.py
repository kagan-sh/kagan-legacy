"""CLI commands for prompt inspection, persona import, and export."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click


@click.group("prompts", help="Prompt inspection, persona import, and export tools.")
def prompts() -> None:
    """Prompt inspection, persona import, and export tools."""


@prompts.command()
@click.option(
    "--type",
    "prompt_type",
    type=click.Choice(["orchestrator", "execution", "review"]),
    required=True,
    help="Which prompt to export.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output file path. Prints to stdout when omitted.",
)
@click.option(
    "--model",
    default="openai/gpt-4.1",
    show_default=True,
    help="Model ID written into the .prompt.yml header.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["yml", "text"]),
    default="yml",
    show_default=True,
    help="Output format: yml (.prompt.yml) or text (raw prompt).",
)
def export(prompt_type: str, output: str | None, model: str, output_format: str) -> None:
    """Export a resolved prompt to .prompt.yml or raw text format."""
    import asyncio

    from kagan.cli._bootstrap import make_client
    from kagan.core import export_prompt_text, export_prompt_yml, write_prompt_file

    settings: dict[str, str] = {}
    try:
        client = make_client()
        settings = asyncio.run(client.settings.get())
    except (OSError, RuntimeError):
        pass  # No DB available — use empty settings (defaults only)

    if output_format == "text":
        content = export_prompt_text(prompt_type, settings)
    else:
        content = export_prompt_yml(prompt_type, settings, model=model)

    if output is None:
        sys.stdout.write(content)
    else:
        dest = write_prompt_file(content, Path(output))
        click.echo(f"Wrote {dest}")


@prompts.group(name="persona", help="Persona preset import and export.")
def persona() -> None:
    """Manage persona presets from GitHub repositories."""


@persona.command(name="import")
@click.argument("repo")
@click.option(
    "--path",
    default=".kagan/personas.json",
    show_default=True,
    help="Path to personas.json",
)
@click.option("--ref", default=None, help="Git ref (branch/tag/sha)")
@click.option(
    "--merge-mode",
    type=click.Choice(["merge", "replace"]),
    default="merge",
    show_default=True,
    help="How to merge with existing personas",
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    help="Auto-confirm low-risk imports without prompting",
)
@click.option(
    "--acknowledge-risk",
    is_flag=True,
    help="Acknowledge high-risk imports (required for high-risk repos)",
)
@click.option(
    "--preview",
    is_flag=True,
    help="Show personas without importing",
)
def import_personas(
    repo: str,
    path: str,
    ref: str | None,
    merge_mode: str,
    yes: bool,
    acknowledge_risk: bool,
    preview: bool,
) -> None:
    """Import persona presets from a GitHub repository.

    Uses progressive trust based on repository reputation:
    - Low risk (established repo, no audit findings): Auto-import with -y
    - Medium risk: Shows audit summary, asks for confirmation
    - High risk: Requires --acknowledge-risk flag

    Examples:
        kagan tools prompts persona import owner/repo
        kagan tools prompts persona import owner/repo -y
        kagan tools prompts persona import owner/repo --preview
        kagan tools prompts persona import owner/repo --acknowledge-risk
    """
    from kagan.cli._bootstrap import make_client, run_async

    async def _do_import() -> None:
        client = make_client()
        try:
            if preview:
                # Preview mode - just show what would be imported
                result = await client.persona_presets.preview_import(repo=repo, path=path, ref=ref)
                _display_preview(result)
                return

            # First, audit the repo to determine trust tier
            audit = await client.persona_presets.audit_repo(repo=repo, path=path, ref=ref)
            trust_tier = audit.get("trust_tier", "high_risk")
            trust_score = audit.get("trust_assessment", {}).get("trust_score", 0.0)
            findings = audit.get("findings", [])
            personas = audit.get("personas", [])

            if trust_tier == "high_risk" and not acknowledge_risk:
                click.echo(click.style("⚠️  High-risk repository detected", fg="red", bold=True))
                click.echo(f"Trust score: {trust_score:.2f}/1.0")
                click.echo()
                _display_findings(findings)
                click.echo()
                click.echo(
                    "This repository has indicators of elevated risk. "
                    "Please review the source carefully before importing."
                )
                click.echo()
                click.echo(
                    "To proceed after review, run with "
                    f"{click.style('--acknowledge-risk', bold=True)}"
                )
                raise click.ClickException("High-risk import requires --acknowledge-risk flag")

            if trust_tier == "medium_risk":
                # Show summary and ask for confirmation
                click.echo(click.style("⚡ Medium-risk repository", fg="yellow", bold=True))
                click.echo(f"Trust score: {trust_score:.2f}/1.0")
                click.echo(f"Personas to import: {len(personas)}")
                click.echo()

                if findings:
                    _display_findings(findings)
                    click.echo()

                if not _confirm_import(repo, personas, default=True):
                    click.echo("Import cancelled.")
                    return

            elif trust_tier == "low_risk":
                # Low risk - can auto-import with -y
                if not yes:
                    click.echo(click.style("✓ Low-risk repository", fg="green"))
                    click.echo(f"Trust score: {trust_score:.2f}/1.0")
                    click.echo(f"Personas to import: {len(personas)}")
                    click.echo()

                    if not _confirm_import(repo, personas, default=True):
                        click.echo("Import cancelled.")
                        return

            # Perform the import
            result = await client.persona_presets.import_from_github(
                repo=repo,
                path=path,
                ref=ref,
                acknowledge_risk=acknowledge_risk,
                merge_mode=merge_mode,
                auto_confirm=yes,
            )

            # Display results
            click.echo()
            click.echo(click.style("✓ Import successful", fg="green", bold=True))
            click.echo(f"Repository: {result.get('repo')}")
            click.echo(f"Imported: {', '.join(result.get('imported', []))}")
            click.echo(f"Total personas: {result.get('total_personas')}")

            if result.get("auto_confirmed"):
                click.echo(click.style("(Auto-confirmed low-risk import)", fg="dim"))

            disclaimer = result.get("disclaimer")
            if disclaimer:
                click.echo()
                click.echo(click.style(f"Note: {disclaimer}", fg="dim", italic=True))

        finally:
            client.close()

    run_async(_do_import())


def _display_preview(result: dict[str, Any]) -> None:
    """Display preview of personas from a repository."""
    click.echo()
    click.echo(click.style(f"Repository: {result.get('repo')}", bold=True))
    click.echo(f"URL: {result.get('repo_url')}")

    trust_tier = result.get("trust_tier", "unknown")
    trust_color = {"low_risk": "green", "medium_risk": "yellow", "high_risk": "red"}.get(
        trust_tier, "white"
    )
    click.echo(f"Trust tier: {click.style(trust_tier, fg=trust_color, bold=True)}")

    assessment = result.get("trust_assessment", {})
    click.echo(f"Trust score: {assessment.get('trust_score', 0):.2f}/1.0")
    click.echo(f"Stars: {assessment.get('stars', 0)}")
    click.echo(f"Repo age: {assessment.get('repo_age_days', 0)} days")

    if result.get("archived"):
        click.echo(click.style("⚠️  Repository is archived", fg="yellow"))

    findings = result.get("findings", [])
    if findings:
        click.echo()
        _display_findings(findings)

    personas = result.get("personas", [])
    click.echo()
    click.echo(click.style(f"Personas ({len(personas)}):", bold=True))
    click.echo()

    for i, p in enumerate(personas, 1):
        click.echo(
            f"  {i}. {click.style(p.get('name', 'Unknown'), bold=True)} ({p.get('key', '')})"
        )
        if p.get("description"):
            click.echo(f"     {p.get('description')}")
        click.echo(f"     Length: {p.get('prompt_length', 0)} chars")
        click.echo()


def _display_findings(findings: list[dict[str, Any]]) -> None:
    """Display audit findings."""
    click.echo(click.style("Security Findings:", bold=True))
    for finding in findings:
        severity = finding.get("severity", "unknown")
        color = {"high": "red", "medium": "yellow", "low": "blue"}.get(severity, "white")
        click.echo(
            f"  [{click.style(severity.upper(), fg=color, bold=True)}] "
            f"{finding.get('persona', 'unknown')}"
        )
        click.echo(f"    {finding.get('message', '')}")
        evidence = finding.get("evidence", [])
        if evidence:
            click.echo(f"    Evidence: {', '.join(str(e) for e in evidence)}")


def _confirm_import(repo: str, personas: list[dict[str, Any]], default: bool = True) -> bool:
    """Ask user to confirm import with option to preview."""
    click.echo(f"Import {len(personas)} persona(s) from {repo}?", nl=False)

    # Build options string
    options = " [Y/n/preview]" if default else " [y/N/preview]"
    click.echo(options + ": ", nl=False)

    while True:
        response = click.getchar()
        click.echo(response)  # Echo the character

        response_lower = response.lower()

        if response_lower == "\r" or response_lower == "\n":
            # Enter key - use default
            return default
        elif response_lower == "y":
            return True
        elif response_lower == "n":
            return False
        elif response_lower == "p":
            # Show detailed preview
            click.echo()
            click.echo(click.style("Detailed Preview:", bold=True))
            click.echo()
            for p in personas:
                click.echo(
                    f"  {click.style(p.get('name', 'Unknown'), bold=True)} ({p.get('key', '')})"
                )
                if p.get("description"):
                    click.echo(f"    Description: {p.get('description')}")
                preview = p.get("prompt_preview", "")
                if preview:
                    lines = preview.split("\n")[:3]
                    click.echo(f"    Preview: {' '.join(lines)[:100]}...")
                click.echo()
            click.echo(f"Import {len(personas)} persona(s) from {repo}?", nl=False)
            click.echo(options + ": ", nl=False)
        elif response_lower == "\x03":
            # Ctrl+C
            raise click.Abort()


@persona.command(name="export")
@click.argument("repo")
@click.option("--path", default=".kagan/personas.json", show_default=True)
@click.option("--branch", default=None, help="Target branch (default: repo default)")
@click.option("--message", "commit_message", default="chore: publish kagan persona presets")
def export_personas(repo: str, path: str, branch: str | None, commit_message: str) -> None:
    """Export local persona presets to GitHub.

    Example:
        kagan tools prompts persona export owner/repo
    """
    from kagan.cli._bootstrap import make_client, run_async

    async def _do_export() -> None:
        client = make_client()
        try:
            result = await client.persona_presets.export_to_github(
                repo=repo, path=path, branch=branch, commit_message=commit_message
            )
            click.echo(click.style("✓ Export successful", fg="green", bold=True))
            click.echo(f"Repository: {result.get('repo')}")
            click.echo(f"Personas exported: {result.get('persona_count')}")
            click.echo(f"File: {result.get('path')}")
        finally:
            client.close()

    run_async(_do_export())


@persona.command(name="audit")
@click.argument("repo")
@click.option("--path", default=".kagan/personas.json", show_default=True)
@click.option("--ref", default=None, help="Git ref to audit")
def audit_personas(repo: str, path: str, ref: str | None) -> None:
    """Audit a persona preset repository without importing.

    Example:
        kagan tools prompts persona audit owner/repo
    """
    from kagan.cli._bootstrap import make_client, run_async

    async def _do_audit() -> None:
        client = make_client()
        try:
            result = await client.persona_presets.audit_repo(repo=repo, path=path, ref=ref)
            _display_preview(result)
        finally:
            client.close()

    run_async(_do_audit())


@persona.command(name="whitelist")
def whitelist_personas() -> None:
    """List trusted persona preset repositories."""
    from kagan.cli._bootstrap import make_client, run_async

    async def _do_list() -> None:
        client = make_client()
        try:
            result = await client.persona_presets.whitelist_list()
            click.echo(click.style("Trusted Persona Repositories", bold=True))
            click.echo()

            registry = result.get("registry_whitelist", [])
            if registry:
                click.echo(click.style("Registry whitelist:", fg="green"))
                for r in registry:
                    click.echo(f"  ✓ {r}")
                click.echo()

            user = result.get("user_whitelist", [])
            if user:
                click.echo(click.style("Your whitelist:", fg="blue"))
                for r in user:
                    click.echo(f"  ✓ {r}")
            else:
                click.echo("Your whitelist is empty.")
        finally:
            client.close()

    run_async(_do_list())


@persona.command(name="trust")
@click.argument("repo")
def trust_persona_repo(repo: str) -> None:
    """Add a repository to your persona preset trust list.

    Example:
        kagan tools prompts persona trust owner/repo
    """
    from kagan.cli._bootstrap import make_client, run_async

    async def _do_trust() -> None:
        client = make_client()
        try:
            result = await client.persona_presets.whitelist_add(repo)
            click.echo(click.style(f"✓ Added {repo} to whitelist", fg="green"))
            click.echo("Trusted repositories:")
            for r in result.get("user_whitelist", []):
                click.echo(f"  ✓ {r}")
        finally:
            client.close()

    run_async(_do_trust())


@persona.command(name="untrust")
@click.argument("repo")
def untrust_persona_repo(repo: str) -> None:
    """Remove a repository from your persona preset trust list.

    Example:
        kagan tools prompts persona untrust owner/repo
    """
    from kagan.cli._bootstrap import make_client, run_async

    async def _do_untrust() -> None:
        client = make_client()
        try:
            result = await client.persona_presets.whitelist_remove(repo)
            click.echo(click.style(f"✓ Removed {repo} from whitelist", fg="green"))
            click.echo("Trusted repositories:")
            for r in result.get("user_whitelist", []):
                click.echo(f"  ✓ {r}")
        finally:
            client.close()

    run_async(_do_untrust())
