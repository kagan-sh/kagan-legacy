"""Reusable Hypothesis strategies for Kagan tests."""

from __future__ import annotations

from typing import Any

from hypothesis import strategies as st

from kagan.database.models import Ticket, TicketPriority, TicketStatus, TicketType

# =============================================================================
# Atomic Strategies
# =============================================================================

# Valid ticket titles: 1-200 chars, non-empty after strip, no null bytes
valid_ticket_titles = st.text(min_size=1, max_size=200).filter(
    lambda x: x.strip() and "\x00" not in x
)

# Invalid titles for boundary testing
empty_titles = st.just("")
oversized_titles = st.text(min_size=201, max_size=250)

# Enum strategies
statuses = st.sampled_from(list(TicketStatus))
priorities = st.sampled_from(list(TicketPriority))
ticket_types = st.sampled_from(list(TicketType))

# Plain ASCII text (no ANSI escapes)
plain_text = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),  # No surrogates
        blacklist_characters="\x1b\x00",  # No escape or null
    ),
    min_size=0,
    max_size=500,
)

# Text that may contain ANSI escape sequences
ansi_codes = st.sampled_from(
    [
        "\x1b[31m",  # Red
        "\x1b[32m",  # Green
        "\x1b[0m",  # Reset
        "\x1b[1m",  # Bold
        "\x1b[38;5;196m",  # 256-color
        "\x1b[38;2;255;0;0m",  # Truecolor
        "\x1b[A",  # Cursor up
        "\x1b[2K",  # Clear line
        "\x1b[1G",  # Cursor to column 1
        "\x1b]0;Title\x07",  # OSC title
        "\x1bM",  # Reverse line feed
    ]
)


@st.composite
def text_with_ansi(draw: st.DrawFn) -> str:
    """Generate text interspersed with ANSI escape codes."""
    parts: list[str] = []
    num_parts = draw(st.integers(min_value=1, max_value=5))
    for _ in range(num_parts):
        if draw(st.booleans()):
            parts.append(draw(ansi_codes))
        parts.append(draw(plain_text))
    if draw(st.booleans()):
        parts.append(draw(ansi_codes))
    return "".join(parts)


# =============================================================================
# Signal Strategies
# =============================================================================

# Valid signal tags
signal_tags = st.sampled_from(
    [
        "<complete/>",
        "<COMPLETE/>",
        "<complete />",
        "<continue/>",
        "<CONTINUE/>",
        '<blocked reason="test"/>',
        '<approve summary="done"/>',
        '<approve summary="done" approach="pattern" key_files="src/main.py"/>',
        '<reject reason="fail"/>',
    ]
)

# Reason text for blocked/approve/reject signals
reason_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        blacklist_characters='"<>',
    ),
    min_size=1,
    max_size=100,
).filter(lambda x: x.strip())


@st.composite
def blocked_signals(draw: st.DrawFn) -> str:
    """Generate blocked signal with reason."""
    reason = draw(reason_text)
    return f'<blocked reason="{reason}"/>'


@st.composite
def approve_signals(draw: st.DrawFn) -> str:
    """Generate approve signal with summary and optional approach/key_files."""
    summary = draw(reason_text)
    parts = [f'summary="{summary}"']

    # Optionally include approach
    if draw(st.booleans()):
        approach = draw(reason_text)
        parts.append(f'approach="{approach}"')

    # Optionally include key_files
    if draw(st.booleans()):
        key_files = draw(reason_text)
        parts.append(f'key_files="{key_files}"')

    return f"<approve {' '.join(parts)}/>"


@st.composite
def reject_signals(draw: st.DrawFn) -> str:
    """Generate reject signal with reason."""
    reason = draw(reason_text)
    return f'<reject reason="{reason}"/>'


@st.composite
def text_with_signal(draw: st.DrawFn) -> tuple[str, str]:
    """Generate text containing a signal, return (full_text, signal_tag)."""
    prefix = draw(plain_text)
    signal = draw(signal_tags)
    suffix = draw(plain_text)
    return (f"{prefix}{signal}{suffix}", signal)


# =============================================================================
# Composite Strategies
# =============================================================================


@st.composite
def tickets(draw: st.DrawFn, **overrides) -> Ticket:
    """Generate a valid Ticket with optional overrides.

    Usage:
        # Random ticket
        ticket = draw(tickets())

        # Ticket with specific status
        ticket = draw(tickets(status=TicketStatus.IN_PROGRESS))
    """
    return Ticket(
        title=overrides.get("title", draw(valid_ticket_titles)),
        status=overrides.get("status", draw(statuses)),
        priority=overrides.get("priority", draw(priorities)),
        ticket_type=overrides.get("ticket_type", draw(ticket_types)),
    )


# =============================================================================
# Todo/Plan Entry Strategies
# =============================================================================

# Valid todo statuses for PlanEntry
todo_statuses = st.sampled_from(["pending", "in_progress", "completed", "failed"])

# Safe text content for todos (no XML special chars)
safe_todo_content = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        blacklist_characters="<>&\"'",
    ),
    min_size=1,
    max_size=50,
).filter(lambda x: x.strip())  # Must have non-whitespace content


@st.composite
def valid_todo_xml(draw: st.DrawFn) -> tuple[str, int]:
    """Generate valid todos XML and expected count.

    Returns:
        Tuple of (XML string with <todos> wrapper, expected todo count)
    """
    n_todos = draw(st.integers(min_value=0, max_value=5))
    todos = []
    for _ in range(n_todos):
        title = draw(safe_todo_content)
        status = draw(todo_statuses)
        todos.append(f'<todo status="{status}">{title}</todo>')
    return f"<todos>{''.join(todos)}</todos>", n_todos


@st.composite
def valid_todo_with_fields(draw: st.DrawFn) -> tuple[str, str, str]:
    """Generate a single todo XML with known content and status.

    Returns:
        Tuple of (XML string with <todos> wrapper, content, status)
    """
    content = draw(safe_todo_content)
    status = draw(todo_statuses)
    xml = f'<todos><todo status="{status}">{content}</todo></todos>'
    return xml, content, status


# =============================================================================
# Form and UI Strategies
# =============================================================================


@st.composite
def ticket_form_data(draw: st.DrawFn) -> dict[str, Any]:
    """Generate form data for ticket creation/editing.

    Returns dict with title, description, priority, ticket_type, acceptance_criteria.
    """
    title = draw(valid_ticket_titles)
    description = draw(
        st.none()
        | st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",),
                blacklist_characters="\x00",
            ),
            min_size=0,
            max_size=1000,
        )
    )
    priority = draw(priorities)
    ticket_type = draw(ticket_types)
    num_criteria = draw(st.integers(min_value=0, max_value=5))
    acceptance_criteria = [draw(safe_todo_content) for _ in range(num_criteria)]
    return {
        "title": title,
        "description": description,
        "priority": priority,
        "ticket_type": ticket_type,
        "acceptance_criteria": acceptance_criteria,
    }


@st.composite
def permission_options(draw: st.DrawFn) -> list[dict[str, str]]:
    """Generate permission option lists for PermissionPrompt.

    Returns list of dicts with kind, name, optionId keys.
    Options include: allow_once, allow_always, reject_once
    """
    option_kinds = ["allow_once", "allow_always", "reject_once"]
    option_names = ["Allow once", "Allow always", "Reject once"]

    # Generate 1-3 options
    num_options = draw(st.integers(min_value=1, max_value=3))
    indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=2),
            min_size=num_options,
            max_size=num_options,
            unique=True,
        )
    )

    return [
        {
            "kind": option_kinds[i],
            "name": option_names[i],
            "optionId": f"option_{i}",
        }
        for i in indices
    ]


# =============================================================================
# Chat and Planner Strategies
# =============================================================================


@st.composite
def chat_messages(draw: st.DrawFn, min_size: int = 0, max_size: int = 10) -> list[dict[str, str]]:
    """Generate chat message history for planner tests.

    Returns list of dicts with role (user/assistant) and content.
    """
    num_messages = draw(st.integers(min_value=min_size, max_value=max_size))
    messages = []
    for i in range(num_messages):
        # Alternate roles, starting with user
        role = "user" if i % 2 == 0 else "assistant"
        content = draw(
            st.text(
                alphabet=st.characters(
                    blacklist_categories=("Cs",),
                    blacklist_characters="\x00",
                ),
                min_size=1,
                max_size=200,
            ).filter(lambda x: x.strip())
        )
        messages.append({"role": role, "content": content})
    return messages


@st.composite
def pending_plans(draw: st.DrawFn) -> list[Ticket]:
    """Generate a list of pending plan tickets.

    Returns 1-5 tickets, all with BACKLOG status.
    """
    num_tickets = draw(st.integers(min_value=1, max_value=5))
    return [draw(tickets(status=TicketStatus.BACKLOG)) for _ in range(num_tickets)]
