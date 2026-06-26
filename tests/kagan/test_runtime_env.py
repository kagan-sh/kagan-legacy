"""The subprocess env allowlist must never leak parent secrets."""

import pytest

from kagan.runtime_env import (
    build_sanitized_subprocess_environment,
    strip_noisy_environment_variables,
)


@pytest.mark.unit
@pytest.mark.fast
def test_allowlist_passes_essentials_and_drops_everything_else() -> None:
    base = {
        "PATH": "/usr/bin",
        "HOME": "/home/me",
        "AWS_SECRET_ACCESS_KEY": "leak",  # secret
        "PYTHONPATH": "/inject",  # interpreter override
        "RANDOM_VAR": "x",  # unknown
    }
    env = build_sanitized_subprocess_environment(base, platform_name="linux")

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/home/me"
    # Only allowlisted names survive; the secret and everything unknown are gone.
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "PYTHONPATH" not in env
    assert "RANDOM_VAR" not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0"


@pytest.mark.unit
@pytest.mark.fast
def test_allow_extra_overrides_and_git_prompt_default() -> None:
    env = build_sanitized_subprocess_environment(
        {"PATH": "/usr/bin"},
        allow_extra={"CUSTOM": "1", "GIT_TERMINAL_PROMPT": "1"},
        platform_name="linux",
    )
    assert env["CUSTOM"] == "1"
    assert env["GIT_TERMINAL_PROMPT"] == "1"  # explicit override wins over the default


@pytest.mark.unit
@pytest.mark.fast
def test_strip_noisy_removes_malloc_vars_in_place() -> None:
    env = {"PATH": "/usr/bin", "MallocStackLogging": "1"}
    removed = strip_noisy_environment_variables(env, platform_name="darwin")
    assert "MallocStackLogging" not in env
    assert removed == ("MallocStackLogging",)
