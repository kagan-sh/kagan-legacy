import shutil
from dataclasses import dataclass, field

from kagan.core.doctor_checks import _AGENT_CLIS


@dataclass(frozen=True, slots=True)
class LaunchRecipe:
    command: list[str]  # headless/non-interactive invocation up to the prompt
    prompt_flag: str | None  # flag the prompt follows; None = positional (path read as a file)
    env: dict[str, str] = field(default_factory=dict)  # per-CLI extra env
    mcp_config_path: str | None = (
        ".mcp.json"  # where to write the agent's MCP client config (None = CLI has no MCP)
    )
    model_flag: str | None = None  # flag a model name follows (None = CLI has no override)
    workdir_flag: str | None = None  # flag the working dir follows (None = CLI honors cwd)


# The only CLI-specific knowledge in the harness (MCP-AGENT-01). Add a row to
# support a new CLI. The harness does NOT run an MCP server; it writes mcp_config_path
# into the worktree so the agent's own MCP client starts `kagan mcp --task-id <id>`
# over stdio. A recipe with mcp_config_path=None has no MCP → .kagan/ask fallback.
#
# command MUST invoke the CLI HEADLESS (no interactive TUI) and MUST NOT enable the
# CLI's own read-only/plan sandbox: kagan withholds writes for read-only passes with a
# 0o444 chmod copy that keeps `.kagan/` writable so the agent can still report. A CLI
# sandbox flag (claude --permission-mode=plan, codex -s read-only) blocks that report
# write too — it severs the agent's only channel (verified, R-002) — so it is never used.
# Every recipe is verified headless + report-capable (writes `.kagan/ask`) under the
# 0o444 chmod copy; see test_recipes / R-002 repro.
#   claude:   `-p` prints and exits (bare claude opens an interactive session).
#   codex:    `exec` is the non-interactive subcommand (bare codex opens the TUI);
#             `--skip-git-repo-check` is required because the read-only sandbox copy is a
#             throwaway tmpdir, not a git repo, and codex exec otherwise refuses to start.
#             `-s workspace-write` is required because `codex exec` DEFAULTS to its own
#             read-only filesystem sandbox — under it the agent gets "operation not
#             permitted: .kagan/ask" and reports nothing (verified, R-002 follow-up probe).
#             workspace-write lets it write the report; the 0o444 chmod copy still blocks
#             every tracked file, so this is NOT a write grant to the repo — it is the
#             write-CHANNEL grant the report needs. (read-only would re-break reporting.)
#   kimi:     `-p <prompt>` runs one prompt non-interactively (bare kimi reads the
#             positional arg as a SUBCOMMAND and errors); the prompt value is read as a
#             file when it is a path. `--yolo` cannot combine with `-p`, so it is unused.
#   opencode: `run` is the headless subcommand; `--dangerously-skip-permissions` is
#             required or its permission engine auto-rejects every write incl. the report,
#             and `--dir` (workdir_flag) pins it to the sandbox — without it opencode
#             walks up to the nearest project root and ignores cwd entirely.
#   gemini:   DELIBERATELY NOT supported (product decision, R-002). gemini has a
#             headless `-p` and a write path (`--approval-mode=yolo`/`-y`), so it is not a
#             technical block — it is intentionally excluded from the supported tier and
#             must not be re-added without a product decision to widen the tier.
RECIPES: dict[str, LaunchRecipe] = {
    "claude": LaunchRecipe(["claude", "-p"], prompt_flag=None, model_flag="--model"),
    "codex": LaunchRecipe(
        ["codex", "exec", "--skip-git-repo-check", "-s", "workspace-write"],
        prompt_flag=None,
        model_flag="--model",
    ),
    "kimi": LaunchRecipe(["kimi"], prompt_flag="-p", mcp_config_path=None, model_flag="--model"),
    "opencode": LaunchRecipe(
        ["opencode", "run", "--dangerously-skip-permissions"],
        prompt_flag=None,
        model_flag="--model",
        workdir_flag="--dir",
    ),
}

assert set(_AGENT_CLIS) <= set(RECIPES), "every doctor CLI needs a recipe"


def recipe_for(cli: str) -> LaunchRecipe:
    return RECIPES.get(cli) or LaunchRecipe([cli], prompt_flag=None)


def available_clis(path: str | None = None) -> list[str]:
    return [cli for cli in _AGENT_CLIS if shutil.which(cli, path=path)]


__all__ = ["RECIPES", "LaunchRecipe", "available_clis", "recipe_for"]
