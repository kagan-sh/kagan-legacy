"""Tests for command router registration behavior."""

from __future__ import annotations

import re

import pytest

from kagan.core.commands import build_command_router
from kagan.core.policy import CommandMetadata, collect_command_methods


def test_command_router_includes_all_registered_operations() -> None:
    router = build_command_router()
    command_keys = {
        (metadata.capability, metadata.method)
        for module_name in (
            "kagan.core.commands.tasks",
            "kagan.core.commands.projects",
            "kagan.core.commands.automation",
            "kagan.core.commands.workspaces",
            "kagan.core.commands.plugins",
        )
        for _name, _fn, metadata in collect_command_methods(__import__(module_name, fromlist=["*"]))
    }

    assert all(router.has_command(capability, method) for capability, method in command_keys)
    assert router.has_command("jobs", "submit")
    assert router.has_command("sessions", "create")
    assert router.has_command("tui", "api_call")


def test_router_raises_for_duplicate_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_metadata = CommandMetadata(
        capability="tasks",
        method="get",
        profile="viewer",
        mutating=False,
        description="",
    )
    monkeypatch.setattr(
        "kagan.core.commands.collect_command_methods",
        lambda _obj: [("duplicate", object(), fake_metadata)],
    )

    with pytest.raises(RuntimeError, match=re.escape("Duplicate command registration")):
        build_command_router()
