---
title: Upgrades and reset
description: Update Kagan safely and reset local state when needed
icon: material/update
---

# Upgrades and reset

## Update

```bash
kagan update --check    # check only
kagan update            # install
kagan update --force    # skip confirmation
kagan update --prerelease
```

Skip startup check: `KAGAN_SKIP_UPDATE_CHECK=1`

## Reset

`kagan reset` removes config/data/cache/worktrees. Destructive.

```bash
kagan reset
kagan reset --force     # no prompt
```

Before: stop other sessions, export logs if needed. After: run `kagan`, reopen project, reconfigure MCP.
