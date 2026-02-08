# Troubleshooting

Common issues and solutions when running Kagan.

## Windows

### Microsoft Visual C++ Redistributable

Some Python packages used by Kagan include native extensions that require the
Microsoft Visual C++ Redistributable. If you see build errors mentioning missing
`vcruntime` or `cl.exe`, install the redistributable:

**Download:** [Microsoft Visual C++ Redistributable](https://go.microsoft.com/fwlink/?LinkID=135170)

After installing, restart your terminal and retry the Kagan installation.

### Windows Installation (PowerShell)

The recommended way to install Kagan on Windows is with the all-in-one installer that
bundles `uv` and a compatible Python version:

```powershell
iwr -useb uvget.me/install.ps1 -OutFile install.ps1; .\install.ps1 kagan
```

Alternatively, if you already have `uv` and Python 3.12+ installed:

```powershell
uv tool install kagan
```

### PAIR Mode on Windows

Windows does not support tmux natively. Kagan defaults to VS Code as the PAIR terminal
backend on Windows. You can also use Cursor:

```toml
[general]
default_pair_terminal_backend = "vscode"  # or "cursor"
```

Make sure `code` (VS Code) or `cursor` is available in your PATH.

## macOS / Linux

### tmux Not Found

PAIR mode defaults to tmux on macOS and Linux. Install it:

```bash
# macOS
brew install tmux

# Debian / Ubuntu
sudo apt install tmux

# Fedora / RHEL
sudo dnf install tmux
```

Alternatively, switch to VS Code or Cursor as the PAIR backend:

```toml
[general]
default_pair_terminal_backend = "vscode"
```

### Permission Denied on Install Script

If the `curl` install script fails with a permission error:

```bash
curl -fsSL https://uvget.me/install.sh | bash -s -- kagan
```

Try running with explicit permission:

```bash
curl -fsSL https://uvget.me/install.sh -o install.sh && chmod +x install.sh && ./install.sh kagan
```

## General

### Agent Not Detected

Kagan auto-detects installed AI CLI agents on startup. If your agent is not detected:

1. Make sure the agent's CLI binary is in your `PATH`
1. Run `which claude`, `which opencode`, `which gemini`, etc. to verify
1. Restart your terminal after installing an agent
1. Check the Debug Log (++f12++) for detection details

### Instance Lock Error

Kagan enforces one instance per repository. If you see "instance locked":

1. Close any other running Kagan instances for the same repo
1. If the lock is stale (e.g. after a crash), use `kagan reset` to clean up
1. Or delete the lock file manually from the XDG data directory

### Merge Conflicts

If a merge fails in REVIEW:

1. Kagan shows merge readiness (Ready / At Risk / Blocked) before you merge
1. Use the resolve action in Task Details to open a terminal in the merge worktree
1. Fix conflicts manually, then retry the merge
1. Consider enabling `serialize_merges = true` in config to reduce conflicts when running
   multiple parallel agents

### Small Terminal Window

Kagan requires a minimum terminal size of 80 columns by 20 rows. If the UI looks broken,
resize your terminal window or reduce the font size.

### Database Reset

If you need a fresh start:

```bash
# Interactive reset (choose what to reset)
kagan reset

# Nuclear reset (removes all data)
kagan reset --force
```

Data is stored in XDG-compliant locations:

- Database: `~/.local/share/kagan/kagan.db`
- Config: `~/.config/kagan/config.toml`
- Worktrees: system temp directory (e.g., `/var/tmp/kagan/worktrees/`)
