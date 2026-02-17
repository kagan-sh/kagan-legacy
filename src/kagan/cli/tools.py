"""CLI tools for stateless one-shot operations."""

from __future__ import annotations

import asyncio
import re
import textwrap
from pathlib import Path

import click
from rich.console import Console

TOOL_CHOICES = ("claude", "opencode")


def _get_default_tool() -> str:
    """Auto-detect the first available AI tool."""
    from kagan.core.builtin_agents import get_all_agent_availability

    for availability in get_all_agent_availability():
        if availability.is_available:
            return availability.agent.config.short_name
    return "claude"


@click.group()
def tools() -> None:
    """Stateless developer utilities."""
    pass


@tools.command()
@click.argument("prompt", required=False, default=None)
@click.option(
    "-t",
    "--tool",
    type=click.Choice(TOOL_CHOICES, case_sensitive=False),
    default=None,
    help="AI tool for enhancement (auto-detects if omitted)",
)
@click.option(
    "-f",
    "--file",
    "file_path",
    type=click.Path(exists=True, readable=True, path_type=Path),
    default=None,
    help="Read prompt from a file (supports multiline content)",
)
def enhance(prompt: str | None, tool: str | None, file_path: Path | None) -> None:
    """Enhance a prompt for AI coding assistants.

    \b
    Examples:
        kagan tools enhance "fix the login bug"
        kagan tools enhance "add dark mode" -t opencode
        kagan tools enhance "refactor auth" | pbcopy
        kagan tools enhance --file prompt.txt
        kagan tools enhance -f requirements.md -t claude
    """
    from kagan.core.agents.refiner import PromptRefiner
    from kagan.core.builtin_agents import get_builtin_agent

    if file_path is not None:
        prompt = file_path.read_text().strip()
    elif prompt is None:
        raise click.UsageError("Either provide a PROMPT argument or use --file option")

    console = Console(stderr=True)

    if tool is None:
        tool = _get_default_tool()
        console.print(f"[dim]Using {tool}[/]", highlight=False)

    agent = get_builtin_agent(tool)
    if not agent or not agent.config:
        raise click.ClickException(f"Unknown tool: {tool}")

    agent_config = agent.config

    async def _enhance() -> str:
        refiner = PromptRefiner(Path.cwd(), agent_config)
        try:
            return await refiner.refine(prompt)
        finally:
            await refiner.stop()

    with console.status("[cyan]Enhancing...", spinner="dots"):
        try:
            result = asyncio.run(_enhance())
        except Exception as e:
            console.print(f"[yellow]Enhancement failed: {e}[/]", highlight=False)
            result = prompt

    click.echo(result)


_PLUGIN_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,63}$")


def _to_class_name(plugin_id: str) -> str:
    """Convert a plugin ID like 'my-cool.plugin' to 'MyCoolPlugin'."""
    parts = re.split(r"[_.\-]+", plugin_id)
    return "".join(part.capitalize() for part in parts) + "Plugin"


def _validate_plugin_name(name: str) -> str:
    """Validate and return a normalized plugin name."""
    normalized = name.strip().lower()
    if not _PLUGIN_ID_RE.fullmatch(normalized):
        msg = (
            f"Plugin name '{name}' is invalid. "
            "Must be 3-64 chars, lowercase, start with a letter, "
            "and contain only [a-z0-9_.-]."
        )
        raise click.BadParameter(msg)
    return normalized


_INIT_TEMPLATE = textwrap.dedent('''\
    """{{name}} - Kagan plugin."""

    from __future__ import annotations

    from typing import Any

    from kagan.core.plugins.sdk import (
        PluginManifest,
        PluginOperation,
        PluginPolicyContext,
        PluginPolicyDecision,
        PluginRegistrationApi,
    )
    from kagan.core.policy import CapabilityProfile


    class {{class_name}}:
        """{{description}}"""

        manifest = PluginManifest(
            id="{{plugin_id}}",
            name="{{display_name}}",
            version="0.1.0",
            entrypoint="{{package_name}}.{{module_name}}:{{class_name}}",
            description="{{description}}",
        )

        def register(self, api: PluginRegistrationApi) -> None:
            api.register_operation(
                PluginOperation(
                    plugin_id=self.manifest.id,
                    capability="{{capability}}",
                    method="hello",
                    handler=_hello_handler,
                    minimum_profile=CapabilityProfile.MAINTAINER,
                    mutating=False,
                    description="Hello world operation.",
                )
            )
            api.register_policy_hook(
                plugin_id=self.manifest.id,
                capability="{{capability}}",
                method="hello",
                hook=_hello_policy_hook,
            )


    async def _hello_handler(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        del ctx
        return {
            "success": True,
            "plugin_id": {{class_name}}.manifest.id,
            "message": "Hello from {{display_name}}!",
            "echo": params.get("echo"),
        }


    def _hello_policy_hook(context: PluginPolicyContext) -> PluginPolicyDecision | None:
        if context.params.get("disabled") is True:
            return PluginPolicyDecision(
                allowed=False,
                code="PLUGIN_POLICY_DENIED",
                message=f"Plugin '{context.plugin_id}' denied: disabled=true",
            )
        return None
''')

_PYPROJECT_TEMPLATE = textwrap.dedent("""\
    [build-system]
    requires = ["hatchling"]
    build-backend = "hatchling.build"

    [project]
    name = "{{package_name}}"
    version = "0.1.0"
    description = "{{description}}"
    requires-python = ">=3.12"
    dependencies = ["kagan"]

    [project.entry-points."kagan.plugins"]
    {{plugin_id}} = "{{package_name}}.{{module_name}}:{{class_name}}"
""")

_README_TEMPLATE = textwrap.dedent("""\
    # {{display_name}}

    {{description}}

    ## Installation

    ```bash
    pip install -e .
    ```

    ## Usage

    Register the plugin entry point `{{plugin_id}}` in your Kagan configuration,
    then invoke the `{{capability}}.hello` operation.

    ## Development

    ```bash
    # Run the plugin test
    pytest tests/ -v
    ```
""")

_TEST_TEMPLATE = textwrap.dedent('''\
    """Tests for {{display_name}}."""

    from __future__ import annotations

    from kagan.core.plugins.sdk import PluginRegistry

    from {{package_name}}.{{module_name}} import {{class_name}}


    def test_plugin_registers_successfully() -> None:
        """Plugin registers without errors and has one operation."""
        registry = PluginRegistry()
        registry.register_plugin({{class_name}}())
        manifests = registry.registered_manifests()
        assert any(m.id == "{{plugin_id}}" for m in manifests)


    def test_hello_operation_resolves() -> None:
        """The hello operation is resolvable after registration."""
        registry = PluginRegistry()
        registry.register_plugin({{class_name}}())
        op = registry.resolve_operation("{{capability}}", "hello")
        assert op is not None
        assert op.plugin_id == "{{plugin_id}}"
''')


def _render_template(template: str, variables: dict[str, str]) -> str:
    """Render a template by replacing {{key}} placeholders."""
    result = template
    for key, value in variables.items():
        result = result.replace("{{" + key + "}}", value)
    return result


def _scaffold_plugin(name: str, output_dir: Path) -> Path:
    """Generate a plugin project directory. Returns the project root."""
    plugin_id = _validate_plugin_name(name)
    class_name = _to_class_name(plugin_id)
    package_name = plugin_id.replace("-", "_").replace(".", "_")
    module_name = "plugin"
    capability = package_name
    display_name = plugin_id.replace("-", " ").replace(".", " ").replace("_", " ").title()
    description = f"A Kagan plugin: {display_name}."

    project_root = output_dir / plugin_id
    if project_root.exists():
        msg = f"Directory already exists: {project_root}"
        raise click.ClickException(msg)

    variables = {
        "name": name,
        "plugin_id": plugin_id,
        "class_name": class_name,
        "package_name": package_name,
        "module_name": module_name,
        "capability": capability,
        "display_name": display_name,
        "description": description,
    }

    # Create directory structure
    pkg_dir = project_root / package_name
    pkg_dir.mkdir(parents=True)
    tests_dir = project_root / "tests"
    tests_dir.mkdir()

    # Write files
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / f"{module_name}.py").write_text(_render_template(_INIT_TEMPLATE, variables))
    (project_root / "pyproject.toml").write_text(_render_template(_PYPROJECT_TEMPLATE, variables))
    (project_root / "README.md").write_text(_render_template(_README_TEMPLATE, variables))
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / f"test_{module_name}.py").write_text(_render_template(_TEST_TEMPLATE, variables))

    return project_root


@tools.command("plugin-scaffold")
@click.option(
    "--name",
    required=True,
    help="Plugin ID (e.g. 'my-plugin'). Must be 3-64 chars, lowercase [a-z0-9_.-].",
)
@click.option(
    "--output",
    "output_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (defaults to current directory).",
)
def plugin_scaffold(name: str, output_dir: Path | None) -> None:
    """Generate a new Kagan plugin project from a template.

    \b
    Examples:
        kagan tools plugin-scaffold --name my-plugin
        kagan tools plugin-scaffold --name my-plugin --output /tmp
    """
    if output_dir is None:
        output_dir = Path.cwd()
    output_dir = output_dir.resolve()

    if not output_dir.exists():
        output_dir.mkdir(parents=True)

    project_root = _scaffold_plugin(name, output_dir)
    click.secho(f"Plugin scaffolded at: {project_root}", fg="green", bold=True)
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  cd {project_root}")
    click.echo("  pip install -e .")
    click.echo("  pytest tests/ -v")
