import shutil
from dataclasses import dataclass, field

from kagan.core.doctor_checks import _AGENT_CLIS
from kagan.core.errors import ConfigurationError


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


# Canonical capability tiers — the portable vocabulary a user writes in repo.yaml
# (builder:/reviewer:) instead of a CLI-specific model id. top / mid / fast.
CANONICAL_TIERS: tuple[str, ...] = ("opus", "sonnet", "haiku")

# alias -> that CLI's native --model string. The ONLY model-namespace knowledge kagan
# carries; keep it MINIMAL. A `None` row means the tier has no faithful, VERIFIABLE
# model for that CLI (a cross-vendor "nearest tier" would be a guess) → resolve_model
# fails LOUD rather than silently running the wrong vendor (R-003).
#
# claude  -> the bare tier alias; claude --help documents opus/sonnet/haiku/fable as
#            native aliases it resolves to the latest model itself, so DO NOT pin a
#            drifting full id here — the alias is the stable value.
# opencode-> provider-qualified `opencode/<full-id>` (run --help: "format of
#            provider/model"). A FRESH opencode install has NO literal `anthropic`
#            provider — its claude models ship under opencode's own gateway provider
#            `opencode/`, with NO `-latest` alias, so these are FULL VERSIONED IDS that
#            DRIFT. Refresh from `opencode models` (filter `opencode/claude-*`) when a
#            newer tier model ships.
# codex/kimi -> NO row: OpenAI-/Moonshot-locked, no verifiable claude-tier equivalent.
#            A canonical tier alias on codex/kimi → loud fail; a native id passes through.
_ALIAS_MAP: dict[str, dict[str, str | None]] = {
    "claude": {"opus": "opus", "sonnet": "sonnet", "haiku": "haiku"},
    "opencode": {
        "opus": "opencode/claude-opus-4-8",
        "sonnet": "opencode/claude-sonnet-4-6",
        "haiku": "opencode/claude-haiku-4-5",
    },
}


_CLAUDE_TIERS: frozenset[str] = frozenset((*CANONICAL_TIERS, "fable"))


def _model_vendor_family(value: str) -> str | None:
    """Best-effort vendor family for a repo.yaml model string.

    Returns None when the id is not recognizably cross-vendor — unknown native ids
    pass through to the CLI unchanged."""
    low = value.lower()
    if value in _CLAUDE_TIERS or low.startswith("claude") or "/claude-" in low:
        return "claude"
    if low.startswith("anthropic/"):
        return "claude"
    if low.startswith(("kimi", "moonshot/")):
        return "moonshot"
    if low.startswith(("gpt-", "openai/")):
        return "openai"
    if len(low) >= 2 and low[0] == "o" and low[1].isdigit():
        return "openai"
    return None


def _cli_accepts_family(cli: str, value: str, family: str) -> bool:
    if cli in ("claude", "opencode"):
        if family == "claude":
            return True
        if cli == "opencode" and family == "openai":
            low = value.lower()
            return low.startswith(("openai/", "opencode/"))
        return False
    if cli == "codex":
        return family == "openai"
    if cli == "kimi":
        return family == "moonshot"
    return True


def validate_model_for_cli(cli: str, value: str | None) -> None:
    """Reject a builder/reviewer model the task CLI cannot run.

    Canonical tier aliases go through ``resolve_model`` (vendor-locked CLIs fail loud).
    Detectable cross-vendor native ids (e.g. ``claude-opus`` on codex) fail here;
    genuinely unknown ids pass through."""
    if value is None:
        return
    if value in CANONICAL_TIERS:
        resolve_model(cli, value)
        return
    family = _model_vendor_family(value)
    if family is None:
        return
    if not _cli_accepts_family(cli, value, family):
        cli_vendor = {
            "claude": "Claude",
            "opencode": "Claude",
            "codex": "OpenAI",
            "kimi": "Moonshot",
        }.get(cli, cli)
        model_vendor = {"claude": "Claude", "openai": "OpenAI", "moonshot": "Moonshot"}[family]
        raise ConfigurationError(
            context="model",
            detail=(
                f"model {value!r} is a {model_vendor} model but CLI {cli!r} runs "
                f"{cli_vendor} models; use a {cli}-native id, a canonical tier alias "
                f"({'/'.join(CANONICAL_TIERS)}), or unset for the CLI default"
            ),
        )


def resolve_model(cli: str, value: str | None) -> str | None:
    """Map a repo.yaml builder/reviewer value to the model string the CLI's --model
    flag actually accepts.

    - ``None`` -> ``None`` (omit the flag; the CLI's own default — unchanged behaviour).
    - a value that is NOT a canonical tier alias -> passed through verbatim (a power-user
      native id like ``claude-opus-4-8``, ``o3``, ``opencode/gpt-5``).
    - a canonical tier alias (opus/sonnet/haiku) -> that CLI's native string from the map.
    - a canonical tier alias with NO mapping for this CLI (codex/kimi) -> raises
      ``ConfigurationError`` so the caller fails LOUD. NEVER silently picks a wrong vendor."""
    if value is None:
        return None
    if value not in CANONICAL_TIERS:
        return value
    native = _ALIAS_MAP.get(cli, {}).get(value)
    if native is None:
        raise ConfigurationError(
            context="model",
            detail=(
                f"model alias {value!r} has no mapping for CLI {cli!r} "
                f"(it is OpenAI-/Moonshot-locked, with no verifiable {value} tier); "
                f"set a {cli}-native model id, or unset to use the CLI default"
            ),
        )
    return native


def available_clis(path: str | None = None) -> list[str]:
    return [cli for cli in _AGENT_CLIS if shutil.which(cli, path=path)]


__all__ = [
    "CANONICAL_TIERS",
    "RECIPES",
    "LaunchRecipe",
    "available_clis",
    "recipe_for",
    "resolve_model",
    "validate_model_for_cli",
]
