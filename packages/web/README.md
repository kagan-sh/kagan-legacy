# Kagan Web

React 19 + Jotai + shadcn/Radix web client for Kagan.

The app is built as a static SPA with Vite and served by the Python server at runtime via `kagan web`. It is bundled into the Python package and always talks to the same same-origin server instance that serves it.

## Requirements

- Node.js 18+
- pnpm

## Local Development

```bash
cd packages/web
pnpm install
pnpm run dev
```

## Quality Checks

```bash
cd packages/web
pnpm run typecheck
pnpm run test
pnpm run build
```

## Bundle For Python Server

Build and copy the static assets into `src/kagan/server/_web_static/`:

```bash
uv run poe web-build
```

Equivalent script:

```bash
./scripts/build_web_ui.sh
```

## Architecture Notes

- `src/lib/api/` contains the REST client, WebSocket client, wire types, and crypto helpers
- `src/lib/atoms/` contains the shared Jotai state graph
- `src/components/shared/workspace.tsx` contains the reusable IDE-style panel primitives
- `src/pages/` contains the route-level workspaces: board, task, session redirect, chat, and settings
- global design tokens, typography, and shell styling live in `src/app.css`
