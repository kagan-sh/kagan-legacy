# Event System

Kagan has four event types. They are not interchangeable — each covers a distinct surface and persistence model.

## The four types

### `AgentEvent` — task session events (DB-persisted)

**File:** `src/kagan/core/agent_events.py`
**Persisted to:** `session_events` table via `core/_events.py`

Typed discriminated union (`kind` field) covering the full lifecycle of an agent task session: `AgentStart`, `AgentEnd`, `TurnStart`, `TurnEnd`, plus the shared `MessageStart/Update/End` and `ToolExecutionStart/Update/End` variants from `events_common`.

These are what flows over SSE to the web dashboard and VS Code extension as a task runs.

```python
# Emitted by _sessions.py / _acp.py, consumed by server/_chat_routes.py + clients
from kagan.core.agent_events import AgentEvent, AgentStart, TurnEnd
```

### `SessionEvent` — ORM model for DB storage

**File:** `src/kagan/core/models.py` (`SessionEvent` SQLModel table)

The database row that wraps an `AgentEvent` — it stores `event_type = variant.kind` and `payload = variant.model_dump(mode="json")`. You interact with this model when reading event history from the DB; you never construct it directly — `core/_events.py` writes it.

### `ChatEvent` — chat surface events (in-memory)

**File:** `src/kagan/core/chat/events.py`

Typed discriminated union for the CLI REPL, TUI chat widget, and server chat SSE. Shares the `MessageStart/Update/End` and `ToolExecution*` variants from `events_common`, and adds chat-specific variants like `AssistantChunk`, `ToolCallStart`, `ToolCallProgress`, `SystemMessage`, `UserTurn`, `SessionError`.

These are NOT persisted — they stream through the chat controller in memory.

```python
from kagan.core.chat.events import ChatEvent, AssistantChunk, SessionError
```

### Shared variants — `events_common`

**File:** `src/kagan/core/events_common.py`

Frozen Pydantic models that appear in BOTH `AgentEvent` and `ChatEvent`:
`MessageStart`, `MessageUpdate`, `MessageEnd`, `ToolExecutionStart`, `ToolExecutionUpdate`, `ToolExecutionEnd`.

Import shared variants from here, not from either consumer module.

```python
from kagan.core.events_common import MessageStart, ToolExecutionEnd
```

## Decision guide

| I want to… | Use |
| --- | --- |
| Add a new agent task lifecycle event | New variant in `agent_events.py`, add to `AgentEvent` union |
| Add a new chat-specific UI event | New variant in `chat/events.py`, add to `ChatEvent` union |
| Add an event that appears in both surfaces | New variant in `events_common.py`, re-export from both unions |
| Read task event history from DB | Query `SessionEvent` table via `_db_async` |
| Emit an event during task execution | Call `Events.emit()` in `core/_events.py` |

## Why four types?

- `AgentEvent` and `ChatEvent` are separate because task-session events are DB-persisted and replayed on reconnect, while chat events are ephemeral streaming fragments — different lifecycles, different shapes.
- `events_common` prevents the `Message*` and `ToolExecution*` variants from diverging between the two surfaces.
- `SessionEvent` is the ORM layer — it is not a domain type, just the persistence wrapper.
