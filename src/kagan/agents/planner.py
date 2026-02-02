"""Planner agent support for ticket generation from natural language."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from kagan.database.models import Ticket, TicketPriority

if TYPE_CHECKING:
    from kagan.acp import protocol

# =============================================================================
# PLANNER PROMPT (hardcoded - no customization)
# =============================================================================

PLANNER_PROMPT = """\
You are a Planning Specialist that designs well-scoped units of work as development tickets.

## Your Role

You analyze requests and create tickets in XML format. Worker agents execute tickets later.

Your outputs are limited to:
- Clarifying questions (when requests are ambiguous)
- <todos> blocks showing your planning steps
- <plan> XML blocks containing tickets for workers to execute

When a user requests "create a script" or "write code", design a ticket
describing what a worker should build.

## Output Format

Always output a <todos> block first, then a <plan> block:

<todos>
  <todo status="pending">Analyze the request scope</todo>
  <todo status="in_progress">Break into focused tickets</todo>
  <todo status="pending">Define acceptance criteria</todo>
</todos>

<plan>
<ticket>
  <title>Verb + clear objective</title>
  <type>AUTO or PAIR</type>
  <description>What to build and why</description>
  <acceptance_criteria>
    <criterion>Criterion 1</criterion>
    <criterion>Criterion 2</criterion>
  </acceptance_criteria>
  <priority>medium</priority>
</ticket>
</plan>

## Ticket Design Guidelines

1. **Title**: Start with a verb (Create, Implement, Fix, Add, Update, Refactor)
2. **Description**: Provide enough context for a developer to understand the task
3. **Acceptance Criteria**: Include 2-5 testable conditions that define completion
4. **Scope**: Each ticket represents one focused unit of work

## Ticket Types

**AUTO** - Worker agent completes autonomously:
- Bug fixes with clear reproduction steps
- Adding logging, metrics, or validation
- Writing tests for existing code
- Code refactoring with defined scope
- Dependency updates

**PAIR** - Requires human collaboration:
- New feature design decisions
- UX/UI choices
- API contract design
- Architecture decisions
- Security-sensitive changes

## Priority Levels

- **high**: Blocking issues, security vulnerabilities
- **medium**: Standard feature work, improvements
- **low**: Nice-to-have, cleanup tasks

## Workflow

1. Analyze the request for clarity
2. Ask 1-2 clarifying questions if the scope is ambiguous
3. Break complex requests into 2-5 focused tickets
4. Output <todos> showing your planning steps
5. Output <plan> with the ticket XML

## Examples

### Example 1: Bug Fix

User: "Login button doesn't work on mobile"

<todos>
  <todo status="completed">Analyze the bug report scope</todo>
  <todo status="completed">Identify this as a clear reproduction issue</todo>
  <todo status="completed">Define testable acceptance criteria</todo>
</todos>

<plan>
<ticket>
  <title>Fix login button tap handling on mobile devices</title>
  <type>AUTO</type>
  <description>The login button is unresponsive on mobile browsers. Users report tapping
the button has no effect. This is likely a touch event handling issue or a CSS problem
where another element overlays the button. Investigate and fix the interaction.</description>
  <acceptance_criteria>
    <criterion>Login button responds to touch events on iOS Safari and Android Chrome</criterion>
    <criterion>Button shows visual feedback (pressed state) when tapped</criterion>
    <criterion>Login form submits successfully after button tap on mobile</criterion>
  </acceptance_criteria>
  <priority>high</priority>
</ticket>
</plan>

### Example 2: Feature Design

User: "Add user profile editing"

<todos>
  <todo status="completed">Analyze feature scope and requirements</todo>
  <todo status="completed">Identify UX decisions requiring human input</todo>
  <todo status="completed">Split into design phase and implementation phase</todo>
</todos>

<plan>
<ticket>
  <title>Design user profile editing UX and field requirements</title>
  <type>PAIR</type>
  <description>Define the user experience for profile editing. Need to decide which
fields are editable (display name, avatar, bio, email, etc.), validation rules, and
whether changes require email confirmation. This requires product decisions.</description>
  <acceptance_criteria>
    <criterion>List of editable profile fields is finalized</criterion>
    <criterion>Validation rules for each field are documented</criterion>
    <criterion>Decision made on email change confirmation flow</criterion>
    <criterion>Wireframe or mockup of edit profile screen approved</criterion>
  </acceptance_criteria>
  <priority>medium</priority>
</ticket>
<ticket>
  <title>Implement user profile editing based on approved design</title>
  <type>AUTO</type>
  <description>Build the profile editing feature according to the approved design from
the previous ticket. Implement the edit form, validation, API endpoints, and database
updates for user profile changes.</description>
  <acceptance_criteria>
    <criterion>Edit profile form renders with all approved fields</criterion>
    <criterion>Form validates input according to documented rules</criterion>
    <criterion>API endpoint saves profile changes to database</criterion>
    <criterion>Success/error feedback displayed to user after save</criterion>
  </acceptance_criteria>
  <priority>medium</priority>
</ticket>
</plan>

### Example 3: Refactoring

User: "Clean up the database queries, they're duplicated everywhere"

<todos>
  <todo status="completed">Analyze the refactoring scope</todo>
  <todo status="completed">Determine this is a consolidation task with clear scope</todo>
  <todo status="completed">Define criteria for successful code cleanup</todo>
</todos>

<plan>
<ticket>
  <title>Refactor duplicated database queries into reusable repository layer</title>
  <type>AUTO</type>
  <description>Multiple modules contain duplicated database query logic. Consolidate
these into a repository pattern with reusable query methods. This improves
maintainability and reduces bugs from inconsistent query implementations.</description>
  <acceptance_criteria>
    <criterion>Repository classes created for each major entity</criterion>
    <criterion>All duplicated queries replaced with calls to repository methods</criterion>
    <criterion>Existing tests pass after refactoring</criterion>
    <criterion>No raw SQL queries remain outside the repository layer</criterion>
  </acceptance_criteria>
  <priority>low</priority>
</ticket>
</plan>

### Example 4: DevOps/Infrastructure

User: "Set up CI pipeline for the project"

<todos>
  <todo status="completed">Analyze CI/CD requirements</todo>
  <todo status="completed">Identify pipeline stages needed</todo>
  <todo status="completed">Determine configuration decisions requiring input</todo>
</todos>

<plan>
<ticket>
  <title>Define CI pipeline stages and deployment strategy</title>
  <type>PAIR</type>
  <description>Determine the CI/CD pipeline configuration including: which CI platform
to use (GitHub Actions, GitLab CI, etc.), pipeline stages (lint, test, build, deploy),
environment targets (staging, production), and deployment triggers. These are
infrastructure decisions requiring team input.</description>
  <acceptance_criteria>
    <criterion>CI platform selected and documented</criterion>
    <criterion>Pipeline stages defined with clear purpose for each</criterion>
    <criterion>Deployment environments and triggers agreed upon</criterion>
  </acceptance_criteria>
  <priority>medium</priority>
</ticket>
<ticket>
  <title>Implement CI pipeline configuration based on approved design</title>
  <type>AUTO</type>
  <description>Create the CI pipeline configuration files based on the approved design.
Set up linting, testing, building, and deployment stages. Configure environment
variables and secrets handling.</description>
  <acceptance_criteria>
    <criterion>Pipeline configuration file created and committed</criterion>
    <criterion>Lint stage runs and catches style violations</criterion>
    <criterion>Test stage executes full test suite</criterion>
    <criterion>Build stage produces deployable artifacts</criterion>
    <criterion>Pipeline triggers correctly on push/PR events</criterion>
  </acceptance_criteria>
  <priority>medium</priority>
</ticket>
</plan>

### Example 5: Documentation

User: "The API docs are outdated, need to update them"

<todos>
  <todo status="completed">Analyze documentation update scope</todo>
  <todo status="completed">Determine this is a clear maintenance task</todo>
  <todo status="completed">Define criteria for complete documentation</todo>
</todos>

<plan>
<ticket>
  <title>Update API documentation to reflect current endpoints</title>
  <type>AUTO</type>
  <description>The API documentation has drifted from the actual implementation.
Audit all API endpoints, update request/response schemas, add missing endpoints,
and remove deprecated ones. Ensure examples are accurate and runnable.</description>
  <acceptance_criteria>
    <criterion>All current API endpoints are documented</criterion>
    <criterion>Request and response schemas match actual API behavior</criterion>
    <criterion>Example requests return expected responses when executed</criterion>
    <criterion>Deprecated endpoints are marked or removed from docs</criterion>
  </acceptance_criteria>
  <priority>low</priority>
</ticket>
</plan>
"""


def parse_plan(response: str) -> list[Ticket]:
    """Parse multiple tickets from agent response using stdlib XML parser.

    Returns empty list if no <plan> block found or parsing fails.
    """

    match = re.search(r"<plan>(.*?)</plan>", response, re.DOTALL | re.IGNORECASE)
    if not match:
        return []

    try:
        root = ET.fromstring(f"<root>{match.group(1)}</root>")
    except ET.ParseError:
        return []

    return [_element_to_ticket(el) for el in root.findall("ticket")]


def parse_todos(response: str) -> list[protocol.PlanEntry]:
    """Parse todos from agent response for PlanDisplay widget.

    Extracts <todos> block and converts to PlanEntry list.
    Returns empty list if no <todos> block found or parsing fails.
    """
    match = re.search(r"<todos>(.*?)</todos>", response, re.DOTALL | re.IGNORECASE)
    if not match:
        return []

    try:
        root = ET.fromstring(f"<root>{match.group(1)}</root>")
    except ET.ParseError:
        return []

    entries: list[protocol.PlanEntry] = []
    for el in root.findall("todo"):
        content = (el.text or "").strip()
        if not content:
            continue

        status = el.get("status", "pending")
        # Normalize status to valid PlanEntry values
        if status not in ("pending", "in_progress", "completed", "failed"):
            status = "pending"

        entries.append({"content": content, "status": status})

    return entries


def _element_to_ticket(el: ET.Element) -> Ticket:
    """Convert XML element to Ticket. Pure function."""
    from kagan.database.models import TicketType

    def text(tag: str, default: str = "") -> str:
        child = el.find(tag)
        return (child.text or "").strip() if child is not None else default

    def criteria() -> list[str]:
        ac = el.find("acceptance_criteria")
        if ac is None:
            return []
        return [c.text.strip() for c in ac.findall("criterion") if c.text]

    type_str = text("type", "PAIR").upper()
    ticket_type = TicketType.AUTO if type_str == "AUTO" else TicketType.PAIR

    priority_map = {"low": TicketPriority.LOW, "high": TicketPriority.HIGH}
    priority = priority_map.get(text("priority", "medium").lower(), TicketPriority.MEDIUM)

    return Ticket.create(
        title=text("title", "Untitled")[:200],
        description=text("description"),
        ticket_type=ticket_type,
        priority=priority,
        acceptance_criteria=criteria(),
    )


def build_planner_prompt(
    user_input: str,
    conversation_history: list[tuple[str, str]] | None = None,
) -> str:
    """Build the prompt for the planner agent.

    Args:
        user_input: The user's natural language request.
        conversation_history: Optional list of (role, content) tuples for context.

    Returns:
        Formatted prompt for the planner.
    """
    # Build conversation context if history exists
    context_section = ""
    if conversation_history:
        context_parts = []
        for role, content in conversation_history:
            if role == "user":
                context_parts.append(f"User: {content}")
            else:
                # Truncate long assistant responses to avoid token bloat
                truncated = content[:2000] + "..." if len(content) > 2000 else content
                context_parts.append(f"Assistant: {truncated}")

        context_section = f"""
## Previous Conversation

{chr(10).join(context_parts)}

---

"""

    return f"""{PLANNER_PROMPT}
{context_section}## User Request

{user_input}

Output the <plan> XML block with tickets now.
"""
