"""Agent backend listing, selection, and formatting."""

from typing import TypedDict

from kagan.core import (
    AgentError,
    get_backend_spec,
    list_available_backends,
    list_backend_specs,
    list_backends,
)
from kagan.core import (
    resolve_default_agent_backend as _resolve_default_agent_backend,
)


class AgentBackendAvailability(TypedDict):
    name: str
    available: bool
    reference: bool


def list_registered_agent_backends() -> list[str]:
    return list_backends()


def format_agent_backend_list(backends: list[str], *, current_backend: str | None) -> list[str]:
    lines = ["Available agent backends:"]
    for index, backend in enumerate(backends, start=1):
        try:
            spec = get_backend_spec(backend)
            label = spec.label()
            suffixes = ["reference"] if spec.reference else []
        except AgentError:
            label = backend
            suffixes = []
        if backend == current_backend:
            suffixes.append("current")
        suffix = f" [{' · '.join(suffixes)}]" if suffixes else ""
        lines.append(f"  {index:>2}  {label}{suffix}")
    lines.append("Type `/agents name` or `/agents number` to switch.")
    return lines


def resolve_agent_backend_selection(arg: str, backends: list[str]) -> tuple[str | None, str | None]:
    normalized = arg.strip()
    if not normalized:
        return None, None

    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(backends):
            return backends[index], None
        return None, f"Invalid number. Pick 1-{len(backends)}."

    if normalized in backends:
        return normalized, None

    matches = [backend for backend in backends if backend.startswith(normalized)]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, f"Ambiguous: {', '.join(matches)}. Be more specific."

    return None, f"Unknown agent backend: {normalized!r}. Available: {', '.join(backends)}"


def resolve_agent_command_argument(
    arg: str, backends: list[str]
) -> tuple[bool, str | None, str | None]:
    normalized = arg.strip()
    if normalized in {"", "list"}:
        return True, None, None
    selected, error = resolve_agent_backend_selection(normalized, backends)
    if error:
        return False, None, error
    if selected is None:
        return False, None, format_agent_usage()
    return False, selected, None


def format_agent_usage() -> str:
    return "Usage: `/agents`, `/agents name`, or `/agents number`"


def format_agent_switching(backend: str) -> str:
    return f"Switching to {backend}..."


def list_backends_with_availability() -> list[AgentBackendAvailability]:
    availability = list_available_backends()
    specs = list_backend_specs()
    return [
        {
            "name": name,
            "available": availability.get(name, False),
            "reference": specs[name].reference,
        }
        for name in specs
    ]


def resolve_default_agent_backend(settings: dict[str, str]) -> str:
    return _resolve_default_agent_backend(settings)
