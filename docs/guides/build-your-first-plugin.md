---
title: Build Your First Plugin
description: Walk-through — scaffold, implement, test, and register a Kagan plugin
---

# Build Your First Plugin

This guide walks you through creating a Kagan plugin from scratch using the
`plugin-scaffold` CLI command.  By the end you will have a working plugin that
registers an operation, enforces a policy hook, and can be installed into any
Kagan instance.

**Time:** ~15 minutes.

---

## Prerequisites

| Requirement | Check |
|-------------|-------|
| Python 3.12+ | `python --version` |
| Kagan installed | `kagan --version` |
| pip / uv | `pip --version` or `uv --version` |

---

## 1. Scaffold a new plugin

```bash
kagan tools plugin-scaffold --name my-plugin
```

This creates a directory structure:

```
my-plugin/
├── my_plugin/
│   ├── __init__.py
│   └── plugin.py          # Plugin class + operation + policy hook
├── tests/
│   ├── __init__.py
│   └── test_plugin.py     # Registration and operation tests
├── pyproject.toml          # Package metadata with kagan.plugins entry point
└── README.md
```

You can also specify a custom output directory:

```bash
kagan tools plugin-scaffold --name my-plugin --output ~/projects
```

---

## 2. Explore the generated code

Open `my_plugin/plugin.py`.  The scaffold creates:

- A **plugin class** with a `PluginManifest` and a `register()` method.
- A **hello operation** — an async handler that returns a greeting.
- A **policy hook** — a sync function that can deny requests.

```python
class MyPlugin:
    manifest = PluginManifest(
        id="my-plugin",
        name="My Plugin",
        version="0.1.0",
        entrypoint="my_plugin.plugin:MyPlugin",
        description="A Kagan plugin: My Plugin.",
    )

    def register(self, api: PluginRegistrationApi) -> None:
        api.register_operation(...)
        api.register_policy_hook(...)
```

### Key SDK contracts

| Contract | Purpose |
|----------|---------|
| `PluginManifest` | Metadata: id, name, version, entrypoint |
| `PluginOperation` | Binds a capability/method pair to a handler |
| `PluginRegistrationApi` | Core API passed to `register()` |
| `PluginPolicyHook` | Optional authorization logic |
| `PluginLifecycle` | Optional startup/shutdown hooks |
| `PluginCapabilityProvider` | Explicit capability declarations |

See the full SDK reference in `src/kagan/core/plugins/sdk.py`.

---

## 3. Customize the operation

Edit the handler in `plugin.py` to do something useful:

```python
async def _hello_handler(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    del ctx
    name = params.get("name", "World")
    return {
        "success": True,
        "plugin_id": MyPlugin.manifest.id,
        "message": f"Hello, {name}! Welcome to my plugin.",
        "echo": params.get("echo"),
    }
```

### Adding more operations

Register additional operations in the `register()` method:

```python
def register(self, api: PluginRegistrationApi) -> None:
    api.register_operation(
        PluginOperation(
            plugin_id=self.manifest.id,
            capability="my_plugin",
            method="hello",
            handler=_hello_handler,
            minimum_profile=CapabilityProfile.VIEWER,
            mutating=False,
            description="Return a greeting.",
        )
    )
    api.register_operation(
        PluginOperation(
            plugin_id=self.manifest.id,
            capability="my_plugin",
            method="goodbye",
            handler=_goodbye_handler,
            minimum_profile=CapabilityProfile.VIEWER,
            mutating=False,
            description="Return a farewell.",
        )
    )
```

---

## 4. Run the tests

```bash
cd my-plugin
pip install -e .
pytest tests/ -v
```

The scaffold includes two tests:

1. **Registration test** — verifies the plugin registers without errors.
2. **Operation resolution test** — verifies the hello operation is discoverable.

---

## 5. Add lifecycle hooks (optional)

Implement the `PluginLifecycle` protocol to run code at startup/shutdown:

```python
from kagan.core.bootstrap import AppContext

class MyPlugin:
    # ... manifest and register() ...

    async def on_core_startup(self, ctx: AppContext) -> None:
        """Runs after core initialization."""
        pass

    async def on_core_shutdown(self, ctx: AppContext) -> None:
        """Runs during core teardown."""
        pass
```

---

## 6. Declare capabilities explicitly (optional)

For strict contract validation, implement `PluginCapabilityProvider`:

```python
from kagan.core.plugins.sdk import PluginCapabilityProvider, PluginCapabilitySpec

class MyPlugin(PluginCapabilityProvider):
    # ... manifest and register() ...

    @property
    def capabilities(self) -> tuple[PluginCapabilitySpec, ...]:
        return (
            PluginCapabilitySpec(
                capability="my_plugin",
                methods=("hello", "goodbye"),
            ),
        )
```

This ensures the registry validates that declared capabilities match registered
operations exactly.

---

## 7. Plugin entry point

The generated `pyproject.toml` declares the entry point:

```toml
[project.entry-points."kagan.plugins"]
my-plugin = "my_plugin.plugin:MyPlugin"
```

When Kagan discovers plugins, it uses this entry point to find and instantiate
your plugin class.

---

## 8. Contributing UI (optional)

Plugins can contribute actions, forms, and badges to the Kagan TUI via the
`ui_describe` operation.  See the
[Plugin UI Schema](plugin-ui-schema.md) guide for the full schema contract.

---

## Hello Plugin example

Kagan ships a built-in hello plugin example at
`src/kagan/core/plugins/examples/hello.py` that demonstrates:

- Manifest with explicit capability declarations
- A `greet` operation with an async handler
- A policy hook that denies requests when `blocked=true`
- Optional lifecycle hooks (`on_core_startup`, `on_core_shutdown`)

Use it as a complete reference alongside this guide.

---

## Summary

| Step | What you did |
|------|-------------|
| 1 | Scaffolded a plugin project with `kagan tools plugin-scaffold` |
| 2 | Explored the generated plugin class, operation, and policy hook |
| 3 | Customized the operation handler |
| 4 | Ran the generated tests |
| 5 | (Optional) Added lifecycle hooks |
| 6 | (Optional) Declared explicit capabilities |
| 7 | Understood the entry point mechanism |
| 8 | (Optional) Learned about UI contributions |
