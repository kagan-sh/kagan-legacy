"""Field spec tables, category definitions, and option builders for SettingsModal.

Kept separate to hold the verbose tuple data away from the screen's control logic.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from textual.theme import BUILTIN_THEMES

from kagan.core import list_available_backends, list_backend_specs

_KAGAN_THEME_NAMES = {"kagan", "kagan-256"}


def build_theme_options() -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = [
        ("Auto (Kagan Night)", ""),
        ("Kagan Night", "kagan"),
        ("Kagan 256-color", "kagan-256"),
    ]
    for name in sorted(BUILTIN_THEMES):
        options.append((name.replace("-", " ").title(), name))
    return options


def build_agent_backend_options() -> list[tuple[str, str]]:
    availability = list_available_backends()
    specs = list_backend_specs()
    options: list[tuple[str, str]] = []
    for name, spec in specs.items():
        label = spec.label()
        suffix: list[str] = []
        if spec.reference:
            suffix.append("reference")
        if not availability.get(name, False):
            suffix.append("unavailable")
        if suffix:
            label = f"{label} ({', '.join(suffix)})"
        options.append((label, name))
    return options


def valid_theme_names() -> set[str]:
    return {"", *_KAGAN_THEME_NAMES, *BUILTIN_THEMES}


@dataclass(frozen=True)
class SettingCategory:
    id: str
    name: str
    search_terms: tuple[str, ...]
    is_advanced: bool = False


@dataclass(frozen=True)
class SettingFieldSpec:
    kind: Literal["switch", "select", "text", "textarea", "static"]
    label: str = ""
    field_id: str | None = None
    options: tuple[tuple[str, str], ...] = ()
    options_factory: Callable[[], list[tuple[str, str]]] | None = None
    text: str = ""
    classes: str = "settings-field-label-top"


CATEGORIES: list[SettingCategory] = [
    SettingCategory(
        id="essentials",
        name="Essentials",
        search_terms=(
            "agent",
            "backend",
            "theme",
            "appearance",
            "color",
            "instructions",
            "custom",
            "prompt",
            "additional",
            "dotfile",
            "review",
            "strict",
            "planning",
        ),
    ),
    SettingCategory(
        id="workflow",
        name="Workflow",
        search_terms=("review", "strict", "confirm", "auto", "approval", "merge"),
    ),
    SettingCategory(
        id="git",
        name="Git",
        search_terms=("git", "user", "name", "email", "identity", "base", "branch"),
    ),
    SettingCategory(
        id="advanced",
        name="Advanced",
        search_terms=(
            "worktree",
            "strategy",
            "ref",
            "remote",
            "local",
            "init",
            "commit",
            "launcher",
            "startup",
            "recent",
            "attached",
            "popup",
        ),
        is_advanced=True,
    ),
]

CATEGORY_FIELDS: dict[str, tuple[SettingFieldSpec, ...]] = {
    "essentials": (
        SettingFieldSpec(
            "select",
            "Default agent backend",
            "settings-default-agent",
            options_factory=build_agent_backend_options,
        ),
        SettingFieldSpec(
            "select",
            "Review strictness",
            "settings-review-strictness",
            options=(
                ("Strict", "strict"),
                ("Balanced", "balanced"),
                ("Relaxed", "relaxed"),
            ),
        ),
        SettingFieldSpec(
            "select",
            "Theme",
            "settings-theme",
            options_factory=build_theme_options,
        ),
        SettingFieldSpec(
            "select",
            "Planning depth",
            "settings-planning-depth",
            options=(
                ("Always plan", "always"),
                ("Multi-task only", "multi_task"),
                ("Never plan", "never"),
            ),
        ),
        SettingFieldSpec("textarea", "Additional instructions", "settings-additional-instructions"),
        SettingFieldSpec(
            "static",
            text=(
                "[dim]Appended to every agent prompt — your preferences,\n"
                "conventions, and workflow rules.\n\n"
                "Examples: 'Use conventional commits' · "
                "'Always explain tradeoffs first'[/dim]"
            ),
        ),
        SettingFieldSpec("static", field_id="settings-dotfile-status"),
        SettingFieldSpec(
            "static",
            text="[dim]Full prompt overrides live in .kagan/prompts/[/dim]",
        ),
    ),
    "workflow": (
        SettingFieldSpec("switch", "Enable auto review", "settings-auto-review"),
        SettingFieldSpec(
            "switch", "Require approval before merge", "settings-require-review-approval"
        ),
        SettingFieldSpec(
            "switch", "Auto-confirm plans for single tasks", "settings-auto-confirm-single"
        ),
        SettingFieldSpec("switch", "Show reasoning preview", "settings-show-reasoning"),
    ),
    "git": (
        SettingFieldSpec(
            "select",
            "Git user mode",
            "settings-git-user-mode",
            options=(
                ("Kagan Agent (default)", "kagan_agent"),
                ("System git profile", "system_default"),
                ("Custom", "custom"),
            ),
        ),
        SettingFieldSpec("text", "Git user name (custom mode)", "settings-git-user-name"),
        SettingFieldSpec("text", "Git email (custom mode)", "settings-git-user-email"),
        SettingFieldSpec("text", "Default base branch", "settings-default-base-branch"),
    ),
    "advanced": (
        SettingFieldSpec(
            "select",
            "Worktree base ref strategy",
            "settings-base-ref-strategy",
            options=(
                ("Local if ahead", "local_if_ahead"),
                ("Remote", "remote"),
                ("Local", "local"),
            ),
        ),
        SettingFieldSpec("switch", "Auto init git repo", "settings-auto-init-repo"),
        SettingFieldSpec("switch", "Auto create initial commit", "settings-auto-init-commit"),
        SettingFieldSpec(
            "select",
            "Interactive attach launcher",
            "settings-attached-launcher",
            options=(
                ("tmux", "tmux"),
                ("nvim", "nvim"),
                ("vscode", "vscode"),
                ("cursor", "cursor"),
                ("windsurf", "windsurf"),
                ("kiro", "kiro"),
                ("antigravity", "antigravity"),
            ),
        ),
        SettingFieldSpec(
            "select",
            "Default `kagan` startup surface",
            "settings-startup-surface",
            options=(
                ("TUI", "tui"),
                ("Web", "web"),
                ("Chat", "chat"),
                ("Show chooser on next launch", "ask"),
            ),
        ),
        SettingFieldSpec(
            "switch", "TUI: reopen last project on launch", "settings-open-last-project"
        ),
        SettingFieldSpec(
            "switch",
            "Skip attach instructions popup",
            "settings-skip-attached-instructions",
        ),
    ),
}
