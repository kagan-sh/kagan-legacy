---
title: VS Code Extension
description: Install the Kagan VS Code extension from the Marketplace or Open VSX and connect it to your Kagan server
icon: material/microsoft-visual-studio-code
tags:
  - vscode
  - editor
  - ide
---

# VS Code Extension

Use Kagan directly inside VS Code when you want the board, `@kagan` chat, diffs, reviews, and task terminals without leaving your editor.

## Install links

- [Install from Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=kagan.kagan-vscode)
- [Install from Open VSX](https://open-vsx.org/extension/kagan/kagan-vscode)

Use the **Marketplace** build for standard VS Code. Use the **Open VSX** build for VSCodium and other Open VSX-powered editors.

______________________________________________________________________

## What the extension adds

- A native **Kagan** sidebar in the Activity Bar
- `@kagan` chat inside the VS Code Chat panel
- Task diffs in the built-in diff editor
- Review verdicts in the Comments panel
- One-click attach to task terminals and live agent output

______________________________________________________________________

## Install in VS Code

1. Install the Kagan CLI:

   ```bash
   uv tool install kagan
   ```

1. Install the extension:

   ```bash
   code --install-extension kagan.kagan-vscode
   ```

   Or install it in the browser:

   - [Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=kagan.kagan-vscode)
   - [Open VSX](https://open-vsx.org/extension/kagan/kagan-vscode)

1. Open a local repository in VS Code.

1. Open the Chat panel and run `@kagan /status`, or click the **Kagan** icon in the Activity Bar.

The extension connects to `http://localhost:8765` by default and auto-starts `kagan serve` when `kagan` is available on your `PATH`.

______________________________________________________________________

## First-run flow

After install, the fastest way to confirm everything is working is:

```bash
kagan --version
code .
```

Then in VS Code:

1. Open the **Chat** panel
1. Type `@kagan /status`
1. Open the **Kagan** sidebar from the Activity Bar
1. Create or run a task

If the local server is already running, the extension reuses it. If you connect to a remote server, set `kagan.serverUrl` and `kagan.authToken` in VS Code settings.

______________________________________________________________________

## Interactive attach from Kagan into VS Code

If you want Kagan to open interactive tasks in VS Code, set:

```toml
attached_launcher = "vscode"
```

When you attach to a task from the TUI, web dashboard, or CLI, the extension can automatically open the task stream in chat so you can keep editing and watching the agent in one place.

While a task is open in `/watch`, plain follow-up messages in the same chat conversation are sent back to that task. Starting a new VS Code chat conversation resets back to orchestrator chat.

See also: [Managed runs & interactive attach](managed-vs-interactive.md)

______________________________________________________________________

## VS Code extension vs MCP setup

These are different integration paths:

- **VS Code extension**: native Kagan experience inside VS Code
- **MCP setup**: exposes Kagan tools to editors and clients that speak MCP

If you are installing the extension, you do **not** need a `.vscode/mcp.json` file just to use the Kagan sidebar or `@kagan` chat.

Use MCP only when you want a generic MCP client configuration in your editor.

See also: [MCP setup](mcp-setup.md)

______________________________________________________________________

## Troubleshooting

- **Extension cannot connect**: confirm `kagan --version` works in the same shell VS Code inherits
- **Local server did not auto-start**: run `kagan serve` manually once to confirm the CLI is installed and reachable
- **Remote server requires auth**: set `kagan.serverUrl`, `kagan.protocol`, and `kagan.authToken`

More help: [Troubleshooting](../troubleshooting.md)
