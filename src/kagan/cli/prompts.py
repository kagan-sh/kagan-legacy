"""CLI commands for prompt inspection and export."""

from __future__ import annotations

import sys
from pathlib import Path

import click


@click.group("prompts", help="Prompt inspection and export tools.")
def prompts() -> None:
    """Prompt inspection and export tools."""


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
    from kagan.cli._bootstrap import make_client
    from kagan.core._prompt_export import export_prompt_text, export_prompt_yml, write_prompt_yml

    try:
        client = make_client()
        import asyncio

        settings = asyncio.run(client.settings.get())
    except Exception:  # graceful fallback when no DB exists
        settings: dict[str, str] = {}

    if output_format == "text":
        content = export_prompt_text(prompt_type, settings)
    else:
        content = export_prompt_yml(prompt_type, settings, model=model)

    if output is None:
        sys.stdout.write(content)
    else:
        dest = write_prompt_yml(content, Path(output))
        click.echo(f"Wrote {dest}")
