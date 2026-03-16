---
title: Remote access
description: Manage your board from a phone or browser
icon: material/cellphone-link
tags:
  - web
  - server
  - remote
---

# Remote access

Run Kagan on one machine and open the bundled dashboard from another browser. Same board, real-time sync.

**Prerequisites:** Kagan installed and devices able to reach the machine running Kagan (same LAN or Tailscale).

## 1. Start the server

```bash
kagan web --host 0.0.0.0
```

This starts the API server with the bundled web UI. Keep this running.

!!! tip
Omit `--host` to bind to localhost only (same machine). Use `--host 0.0.0.0` when connecting from another device.

## 2. Open the web client

Open one of these URLs in a browser:

- Same machine: `http://127.0.0.1:8765`
- Another device on LAN: `http://<your-lan-ip>:8765` (for example `http://192.168.1.42:8765`)
- Over Tailscale: `http://<tailscale-ip>:8765` or `http://<machine-name>.tailnet.ts.net:8765`

## 3. Open directly

There is no separate browser pairing flow for the dashboard. The web UI is bundled into the wheel and is served directly by `kagan web`.

- Supported path: expose `kagan web` itself on LAN, Tailscale, or your own proxy/VPN setup.
- Unsupported product path: pairing the dashboard to a separate `kagan serve` instance.
- If you expose `kagan web` beyond localhost, that network setup is your responsibility.

## 4. Use it

| Action         | How                                                |
| -------------- | -------------------------------------------------- |
| Create task    | Click or tap **+ New Task**                        |
| Move task      | Drag and drop task cards (board)                   |
| Start agent    | Open task details → **Start run**                  |
| View details   | Click or tap a task card                           |
| Review & merge | Open a REVIEW task → approve / reject / merge      |
| Switch project | Use the project manager in settings                |
| Open locally   | Run `kagan web` on the machine that owns the board |

Changes sync in real-time across all connected clients and the TUI.

______________________________________________________________________

## Server options

```bash
kagan web --help
```

| Flag         | Default     | Description                                  |
| ------------ | ----------- | -------------------------------------------- |
| `--host`     | `127.0.0.1` | Bind address                                 |
| `--port`     | `8765`      | Bind port                                    |
| `--readonly` | off         | Read-only access (no mutations)              |
| `--admin`    | off         | Admin access (delete tasks, manage projects) |

## Advanced: self-hosting for remote access

!!! warning "Early alpha"
Remote self-hosting is for power users. Proceed with due diligence.

For access outside your local network (e.g. over the internet), use a reverse proxy or VPN:

- **Tailscale** (recommended): Install on both machines. Access via `http://<machine-name>.tailnet.ts.net:8765`. No port forwarding needed.
- **Reverse proxy** (nginx, Caddy): Terminate TLS and proxy to `127.0.0.1:8765`.
- **`kagan serve`**: Use this only for programmatic API access or non-dashboard clients. It is not the supported way to host the bundled web dashboard.

Never expose an unauthenticated `kagan web --host 0.0.0.0` to the public internet.

## Troubleshooting

**Can't connect from another device?**
: Check that `--host 0.0.0.0` is set and your firewall allows the port.

**Board out of sync?**
: Refresh the board page and check the WebSocket indicator in settings.

**Port already in use?**
: `kagan web --port 9000` (or any free port).
