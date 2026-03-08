---
title: Plugins
description: Early-stage plugin system for extending Kagan
icon: material/puzzle
---

# Plugins

!!! warning "Early stage"
    The plugin system exists but is not fully fleshed out yet. GitHub import is the only shipping integration — it works as a native feature, not something you configure as a plugin.

    If you have ideas for plugins you'd like to see (Jira import, Linear sync, Slack notifications, custom CI hooks, etc.), tell us:

    - **[GitHub Discussions](https://github.com/kagan-sh/kagan/discussions)** — shape the roadmap
    - **[Feature requests](https://github.com/kagan-sh/kagan/issues/new?template=feature_request.md)** — propose a specific plugin

## GitHub import

GitHub issue import is built into Kagan. No plugin configuration needed.

- **TUI**: Command palette (`Ctrl+P`) → `github import`, or `.` → `github import`
- **CLI**: `kagan import github --repo owner/repo`

[:octicons-arrow-right-24: Full GitHub import guide](../guides/github.md)

## For contributors

The internal plugin system uses Python entry points (`kagan.plugins` group). If you're building a third-party integration, add it to the `[plugins]` discovery list in `config.toml`:

```toml
[plugins]
discovery = [..., "my_package.my_plugin:MyPlugin"]
```

Plugin CLI commands (`kagan plugins sync/list/check`) are gated behind `KAGAN_ENABLE_PLUGIN_CLI=1`. This is intentional — the surface is experimental.
