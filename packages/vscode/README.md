# Kagan VS Code Extension

Native VS Code client for Kagan.

## Connection Behavior

The extension connects to `kagan.serverUrl` on activation.

For local development, the default behavior is:

- auto-connect on startup
- if `kagan.serverUrl` points at `localhost`, `127.0.0.1`, or `::1` and nothing is listening,
  the extension automatically starts `kagan web --no-open`
- if your CLI is installed under a different name or path, set `kagan.serverCommand`

The extension does not auto-start remote servers.

## Settings

- `kagan.serverUrl`: base URL of the Kagan server
- `kagan.autoConnect`: connect automatically on activation
- `kagan.autoStartServer`: auto-start a local Kagan server when `serverUrl` is local
- `kagan.serverCommand`: command used for local auto-start; the extension runs
  `<command> web --no-open`

## Quality Checks

Run these from the repository root:

```bash
pnpm run vscode:typecheck
pnpm run vscode:test:unit
pnpm run vscode:test:integration
pnpm run vscode:test:e2e
```
