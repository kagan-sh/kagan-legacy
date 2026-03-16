# Design

Internal architecture and feature documentation for contributors.
User-facing docs live in `docs/` and are published via mkdocs.

## Structure

```
docs/internal/
  architecture/     # How things work (implementation guidance)
    core.md         # KaganCore SDK
    chat.md         # Chat module, REPL, slash commands
    tui.md          # Textual TUI
    web.md          # React web client
    cli.md          # Click CLI
    mcp.md          # MCP server
    server.md       # HTTP API server (REST + WebSocket)
    plugins.md      # Plugin system
  features/         # What the system does (behavioral catalogs)
    core.md         # Core domain behaviors
    chat.md         # REPL and orchestrator behaviors
    tui.md          # TUI behaviors
    web.md          # Web client behaviors
    cli.md          # CLI behaviors
    mcp.md          # MCP tool behaviors
    server.md       # Server features (REST, WebSocket, API auth)
    plugins.md      # Plugin behaviors
    github_import_user_experience.md # Layman-first GitHub import rollout plan
  testing.md        # Acceptance test commandments
```

## Reading Order

1. **Start here** — skim `features/core.md` for what the system does
1. **Pick a module** — read the matching `architecture/` doc for how it works
1. **Before writing tests** — read `testing.md`

## Conventions

- **Features** describe observable behaviors. Each section maps 1:1 to a test file.
- **Architecture** describes implementation: module layout, data flow, design decisions.
- Architecture docs reference features docs (not the reverse).
- All paths in these docs are relative to the repo root.
