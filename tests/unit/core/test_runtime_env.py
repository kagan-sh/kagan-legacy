"""Unit tests for runtime environment sanitization utilities.

Tests for src/kagan/runtime_env.py covering:
- Essential env var preservation
- Sensitive pattern stripping
- Python var stripping
- allow_extra parameter behavior
- Platform-specific noisy env var handling
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import MutableMapping

import pytest

from kagan.runtime_env import (
    _ESSENTIAL_ENV_POSIX,
    _ESSENTIAL_ENV_WINDOWS,
    _essential_env,
    _is_python_key,
    _is_sensitive_key,
    build_sanitized_subprocess_environment,
    noisy_env_keys,
    sanitize_startup_environment,
    strip_noisy_environment_variables,
)

pytestmark = [pytest.mark.unit]


def _merge_os_environ(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    """Overlay *env* on the process environment (``patch.dict(..., clear=False)``)."""

    for k, v in env.items():
        monkeypatch.setenv(k, v)


def _replace_os_environ(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    """Replace the process environment with *env* (``patch.dict(..., clear=True)``)."""

    for k in list(os.environ):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


class TestIsSensitiveKey:
    """Tests for _is_sensitive_key function."""

    @pytest.mark.parametrize(
        "key",
        [
            "TOKEN",
            "MY_TOKEN",
            "API_TOKEN",
            "GITHUB_TOKEN",
            "OAUTH_TOKEN",
            "KEY",
            "API_KEY",
            "SECRET_KEY",
            "PRIVATE_KEY",
            "SECRET",
            "API_SECRET",
            "CLIENT_SECRET",
            "PASSWORD",
            "DB_PASSWORD",
            "USER_PASSWORD",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_REGION",
            "AZURE_SUBSCRIPTION_ID",
            "AZURE_CLIENT_SECRET",
            "GCP_PROJECT_ID",
            "GCP_SERVICE_ACCOUNT_KEY",
            "OPENAI_API_KEY",
            "OPENAI_ORG_ID",
            "ANTHROPIC_API_KEY",
            "GITHUB_TOKEN",
            "GITHUB_API_KEY",
            "LD_PRELOAD",
            "DYLD_INSERT_LIBRARIES",
        ],
    )
    def test_sensitive_patterns_detected(self, key: str) -> None:
        """Sensitive patterns should be detected regardless of position."""
        assert _is_sensitive_key(key) is True
        # Case insensitivity
        assert _is_sensitive_key(key.lower()) is True
        assert _is_sensitive_key(key.swapcase()) is True

    @pytest.mark.parametrize(
        "key",
        [
            "PATH",
            "HOME",
            "USER",
            "SHELL",
            "PWD",
            "LANG",
            "EDITOR",
            "MY_VAR",
            "FOO",
            "BAR",
            "DATABASE_URL",  # Doesn't match any pattern
            "KEEP",  # Contains KEE but not KEY at word boundary
            "LOOKUP",  # Contains OOK not KEY
        ],
    )
    def test_non_sensitive_keys(self, key: str) -> None:
        """Non-sensitive keys should not be flagged."""
        assert _is_sensitive_key(key) is False

    @pytest.mark.parametrize(
        "key",
        [
            "KEYRING",  # Contains KEY pattern
            "MONKEY",  # Contains KEY pattern
            "WHISKEY",  # Contains KEY pattern
            "TURKEY",  # Contains KEY pattern
        ],
    )
    def test_words_containing_key_pattern(self, key: str) -> None:
        """Words containing KEY substring ARE flagged (pattern matches anywhere)."""
        # Note: The implementation uses substring matching, so these ARE sensitive
        assert _is_sensitive_key(key) is True


class TestIsPythonKey:
    """Tests for _is_python_key function."""

    @pytest.mark.parametrize(
        "key",
        [
            "PYTHONPATH",
            "PYTHONHOME",
            "PYTHON_VERSION",
            "PYTHONUTF8",
            "PYTHONDONTWRITEBYTECODE",
            "pythonpath",  # lowercase
            "PythonPath",  # mixed case
        ],
    )
    def test_python_keys_detected(self, key: str) -> None:
        """Python-specific keys should be detected."""
        assert _is_python_key(key) is True

    @pytest.mark.parametrize(
        "key",
        [
            "PATH",
            "HOME",
            "MY_PYTHON_PATH",  # PYTHON not at start
        ],
    )
    def test_non_python_keys(self, key: str) -> None:
        """Non-Python keys should not be flagged."""
        assert _is_python_key(key) is False

    @pytest.mark.parametrize(
        "key",
        [
            "PYTHONIC",  # Starts with PYTHON - IS flagged (startswith check)
            "PYTHON_ENV",  # Starts with PYTHON - IS flagged
        ],
    )
    def test_python_prefixed_keys_are_flagged(self, key: str) -> None:
        """Keys starting with PYTHON are flagged as Python keys."""
        # Note: The implementation uses startswith, so these ARE Python keys
        assert _is_python_key(key) is True


class TestNoisyEnvKeys:
    """Tests for noisy_env_keys function."""

    def test_darwin_noisy_keys(self) -> None:
        """Darwin (macOS) should have specific noisy keys."""
        keys = noisy_env_keys("darwin")
        assert "MallocStackLogging" in keys
        assert "MallocStackLoggingNoCompact" in keys
        assert "MALLOCSTACKLOGGING" in keys
        assert "MALLOCSTACKLOGGINGNOCOMPACT" in keys

    def test_linux_noisy_keys(self) -> None:
        """Linux should have no noisy keys defined."""
        assert noisy_env_keys("linux") == ()

    def test_win32_noisy_keys(self) -> None:
        """Windows should have no noisy keys defined."""
        assert noisy_env_keys("win32") == ()

    def test_unknown_platform_defaults_to_empty(self) -> None:
        """Unknown platforms should return empty tuple."""
        assert noisy_env_keys("unknown") == ()
        assert noisy_env_keys("freebsd") == ()

    def test_defaults_to_sys_platform(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default should use sys.platform."""
        monkeypatch.setattr(sys, "platform", "darwin")
        keys = noisy_env_keys()
        assert "MallocStackLogging" in keys

        monkeypatch.setattr(sys, "platform", "linux")
        keys = noisy_env_keys()
        assert keys == ()


class TestStripNoisyEnvironmentVariables:
    """Tests for strip_noisy_environment_variables function."""

    def test_removes_darwin_malloc_logging_exact(self) -> None:
        """Should remove exact Darwin malloc logging keys."""
        env: MutableMapping[str, str] = {
            "MallocStackLogging": "1",
            "PATH": "/usr/bin",
            "HOME": "/home/user",
        }
        removed = strip_noisy_environment_variables(env, platform_name="darwin")
        assert "MallocStackLogging" in removed
        assert "MallocStackLogging" not in env
        assert "PATH" in env
        assert "HOME" in env

    def test_removes_darwin_malloc_logging_case_insensitive(self) -> None:
        """Should remove Darwin malloc logging keys case-insensitively."""
        env: MutableMapping[str, str] = {
            "mallocstacklogging": "1",
            "MallocStackLoggingNoCompact": "1",
            "PATH": "/usr/bin",
        }
        removed = strip_noisy_environment_variables(env, platform_name="darwin")
        assert len(removed) == 2
        assert "mallocstacklogging" in removed
        assert "MallocStackLoggingNoCompact" in removed

    def test_removes_darwin_substring_matches(self) -> None:
        """Should remove keys containing mallocstacklogging substring."""
        env: MutableMapping[str, str] = {
            "MY_mallocstacklogging_VAR": "1",
            "PATH": "/usr/bin",
        }
        removed = strip_noisy_environment_variables(env, platform_name="darwin")
        assert "MY_mallocstacklogging_VAR" in removed

    def test_no_removal_on_linux(self) -> None:
        """Should not remove any keys on Linux."""
        env: MutableMapping[str, str] = {
            "MallocStackLogging": "1",
            "PATH": "/usr/bin",
        }
        removed = strip_noisy_environment_variables(env, platform_name="linux")
        assert removed == ()
        assert "MallocStackLogging" in env

    def test_returns_tuple_of_removed_keys(self) -> None:
        """Should return tuple of removed keys."""
        env: MutableMapping[str, str] = {
            "MallocStackLogging": "1",
            "MallocStackLoggingNoCompact": "1",
            "PATH": "/usr/bin",
        }
        removed = strip_noisy_environment_variables(env, platform_name="darwin")
        assert isinstance(removed, tuple)
        assert len(removed) == 2

    def test_defaults_to_sys_platform(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should default to sys.platform when not specified."""
        env: MutableMapping[str, str] = {
            "MallocStackLogging": "1",
            "PATH": "/usr/bin",
        }
        monkeypatch.setattr(sys, "platform", "darwin")
        removed = strip_noisy_environment_variables(env)
        assert "MallocStackLogging" in removed

        env = {"MallocStackLogging": "1", "PATH": "/usr/bin"}
        monkeypatch.setattr(sys, "platform", "linux")
        removed = strip_noisy_environment_variables(env)
        assert "MallocStackLogging" not in removed


class TestSanitizeStartupEnvironment:
    """Tests for sanitize_startup_environment function."""

    def test_removes_noisy_vars_from_os_environ(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should remove noisy variables from os.environ."""
        _merge_os_environ(monkeypatch, {"MallocStackLogging": "1", "PATH": "/usr/bin"})
        monkeypatch.setattr(sys, "platform", "darwin")
        removed = sanitize_startup_environment()
        # Windows uppercases env keys, so compare case-insensitively
        removed_upper = {k.upper() for k in removed}
        assert "MALLOCSTACKLOGGING" in removed_upper
        assert "MallocStackLogging" not in os.environ

    def test_preserves_non_noisy_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should preserve non-noisy variables."""
        test_env = {"PATH": "/usr/bin", "HOME": "/home/user"}
        _replace_os_environ(monkeypatch, test_env)
        monkeypatch.setattr(sys, "platform", "darwin")
        sanitize_startup_environment()
        assert os.environ.get("PATH") == "/usr/bin"
        assert os.environ.get("HOME") == "/home/user"


class TestBuildSanitizedSubprocessEnvironment:
    """Tests for build_sanitized_subprocess_environment function."""

    def test_preserves_essential_vars(self) -> None:
        """Should preserve essential environment variables."""
        base_env = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/user",
            "USER": "testuser",
            "SHELL": "/bin/bash",
            "PWD": "/home/user/project",
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
            "TERM": "xterm-256color",
            "EDITOR": "vim",
            "SSH_AUTH_SOCK": "/tmp/ssh.sock",
            "GIT_CONFIG_GLOBAL": "/home/user/.gitconfig",
        }
        result = build_sanitized_subprocess_environment(base_env, platform_name="linux")
        for key in _ESSENTIAL_ENV_POSIX:
            assert key in result
            assert result[key] == base_env[key]

    def test_skips_missing_essential_vars(self) -> None:
        """Should skip essential variables not present in base_env."""
        base_env = {"PATH": "/usr/bin", "HOME": "/home/user"}
        result = build_sanitized_subprocess_environment(base_env)
        assert "PATH" in result
        assert "HOME" in result
        assert "EDITOR" not in result  # Not in base_env

    def test_strips_sensitive_vars(self) -> None:
        """Should strip variables matching sensitive patterns."""
        base_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "API_KEY": "secret123",
            "GITHUB_TOKEN": "ghp_xxx",
            "AWS_ACCESS_KEY_ID": "AKIAxxx",
            "SECRET_PASSWORD": "hunter2",
        }
        result = build_sanitized_subprocess_environment(base_env)
        assert "PATH" in result
        assert "HOME" in result
        assert "API_KEY" not in result
        assert "GITHUB_TOKEN" not in result
        assert "AWS_ACCESS_KEY_ID" not in result
        assert "SECRET_PASSWORD" not in result

    def test_strips_python_vars(self) -> None:
        """Should strip Python-specific variables."""
        base_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "PYTHONPATH": "/custom/python/path",
            "PYTHONHOME": "/usr/local/python",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        result = build_sanitized_subprocess_environment(base_env)
        assert "PATH" in result
        assert "HOME" in result
        assert "PYTHONPATH" not in result
        assert "PYTHONHOME" not in result
        assert "PYTHONDONTWRITEBYTECODE" not in result

    def test_strips_noisy_vars_per_platform(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should strip noisy variables based on platform."""
        base_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "MallocStackLogging": "1",
        }
        monkeypatch.setattr(sys, "platform", "darwin")
        result = build_sanitized_subprocess_environment(base_env)
        assert "MallocStackLogging" not in result

        # On Linux, MallocStackLogging should not be in base result
        # but let's verify the logic doesn't add it
        base_env_linux = {"PATH": "/usr/bin", "HOME": "/home/user"}
        result_linux = build_sanitized_subprocess_environment(base_env_linux)
        assert "MallocStackLogging" not in result_linux

    def test_allow_extra_adds_extra_vars(self) -> None:
        """Should add extra variables specified in allow_extra."""
        base_env = {"PATH": "/usr/bin", "HOME": "/home/user"}
        allow_extra = {"MY_CUSTOM_VAR": "custom_value", "ANOTHER_VAR": "another_value"}
        result = build_sanitized_subprocess_environment(base_env, allow_extra=allow_extra)
        assert "MY_CUSTOM_VAR" in result
        assert result["MY_CUSTOM_VAR"] == "custom_value"
        assert "ANOTHER_VAR" in result
        assert result["ANOTHER_VAR"] == "another_value"

    def test_allow_extra_overrides_base_env(self) -> None:
        """allow_extra should override values from base_env."""
        base_env = {"PATH": "/usr/bin", "HOME": "/home/user"}
        allow_extra = {"PATH": "/custom/bin", "MY_VAR": "value"}
        result = build_sanitized_subprocess_environment(base_env, allow_extra=allow_extra)
        assert result["PATH"] == "/custom/bin"

    def test_allow_extra_bypasses_sensitive_check(self) -> None:
        """allow_extra variables should bypass sensitive pattern checks."""
        base_env = {"PATH": "/usr/bin", "HOME": "/home/user"}
        allow_extra = {
            "MY_API_KEY": "secret_value",
            "GITHUB_TOKEN": "ghp_xxx",
            "AWS_SECRET": "aws_secret",
        }
        result = build_sanitized_subprocess_environment(base_env, allow_extra=allow_extra)
        assert "MY_API_KEY" in result
        assert result["MY_API_KEY"] == "secret_value"
        assert "GITHUB_TOKEN" in result
        assert "AWS_SECRET" in result

    def test_allow_extra_bypasses_python_check(self) -> None:
        """allow_extra variables should bypass Python-specific checks."""
        base_env = {"PATH": "/usr/bin", "HOME": "/home/user"}
        allow_extra = {
            "PYTHONPATH": "/custom/path",
            "PYTHONHOME": "/custom/python",
        }
        result = build_sanitized_subprocess_environment(base_env, allow_extra=allow_extra)
        assert "PYTHONPATH" in result
        assert result["PYTHONPATH"] == "/custom/path"
        assert "PYTHONHOME" in result

    def test_allow_extra_with_essential_vars(self) -> None:
        """allow_extra should work correctly when essential vars are present."""
        base_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "API_KEY": "should_be_removed",
        }
        allow_extra = {"CUSTOM_VAR": "custom"}
        result = build_sanitized_subprocess_environment(base_env, allow_extra=allow_extra)
        assert "PATH" in result
        assert "HOME" in result
        assert "API_KEY" not in result
        assert "CUSTOM_VAR" in result

    def test_empty_allow_extra(self) -> None:
        """Empty allow_extra should be handled gracefully."""
        base_env = {"PATH": "/usr/bin", "HOME": "/home/user"}
        result = build_sanitized_subprocess_environment(base_env, allow_extra={})
        assert "PATH" in result
        assert "HOME" in result
        assert len(result) == 2

    def test_none_allow_extra(self) -> None:
        """None allow_extra should be handled gracefully."""
        base_env = {"PATH": "/usr/bin", "HOME": "/home/user"}
        result = build_sanitized_subprocess_environment(base_env, allow_extra=None)
        assert "PATH" in result
        assert "HOME" in result
        assert len(result) == 2

    def test_uses_os_environ_when_base_env_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should use os.environ when base_env is None."""
        _replace_os_environ(
            monkeypatch,
            {
                "PATH": "/usr/bin",
                "HOME": "/home/user",
                "API_KEY": "secret",
            },
        )
        result = build_sanitized_subprocess_environment()
        assert "PATH" in result
        assert "HOME" in result
        assert "API_KEY" not in result

    def test_returns_dict(self) -> None:
        """Should return a dictionary."""
        base_env = {"PATH": "/usr/bin", "HOME": "/home/user"}
        result = build_sanitized_subprocess_environment(base_env)
        assert isinstance(result, dict)

    def test_does_not_modify_input(self) -> None:
        """Should not modify the input base_env."""
        base_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "API_KEY": "secret",
        }
        original_keys = set(base_env.keys())
        build_sanitized_subprocess_environment(base_env)
        assert set(base_env.keys()) == original_keys
        assert "API_KEY" in base_env

    def test_combined_sensitive_and_noisy_removal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should handle both sensitive and noisy vars correctly."""
        base_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "API_KEY": "secret",
            "MallocStackLogging": "1",
        }
        monkeypatch.setattr(sys, "platform", "darwin")
        result = build_sanitized_subprocess_environment(base_env)
        assert "PATH" in result
        assert "HOME" in result
        assert "API_KEY" not in result
        assert "MallocStackLogging" not in result

    def test_case_sensitivity_of_sensitive_patterns(self) -> None:
        """Sensitive patterns should be matched case-insensitively."""
        base_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "api_key": "lowercase_secret",  # lowercase
            "Api_Key": "mixed_case_secret",  # mixed case
        }
        result = build_sanitized_subprocess_environment(base_env)
        assert "api_key" not in result
        assert "Api_Key" not in result

    def test_partial_pattern_matches(self) -> None:
        """Partial matches of sensitive patterns should be detected."""
        base_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "MY_TOKEN_HERE": "secret",  # Contains TOKEN
            "THE_API_KEY_VAR": "secret",  # Contains KEY
            "SUPER_SECRET_STUFF": "secret",  # Contains SECRET
        }
        result = build_sanitized_subprocess_environment(base_env)
        assert "MY_TOKEN_HERE" not in result
        assert "THE_API_KEY_VAR" not in result
        assert "SUPER_SECRET_STUFF" not in result

    def test_ld_preload_removed(self) -> None:
        """LD_PRELOAD should be removed as a sensitive pattern."""
        base_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "LD_PRELOAD": "/path/to/library.so",
        }
        result = build_sanitized_subprocess_environment(base_env)
        assert "LD_PRELOAD" not in result

    def test_dyld_insert_libraries_removed(self) -> None:
        """DYLD_INSERT_LIBRARIES should be removed as a sensitive pattern."""
        base_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "DYLD_INSERT_LIBRARIES": "/path/to/library.dylib",
        }
        result = build_sanitized_subprocess_environment(base_env)
        assert "DYLD_INSERT_LIBRARIES" not in result

    def test_cloud_provider_prefixes(self) -> None:
        """Cloud provider prefixes should be detected."""
        base_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "AWS_DEFAULT_REGION": "us-east-1",
            "AZURE_TENANT_ID": "tenant123",
            "GCP_CREDENTIALS": "creds",
        }
        result = build_sanitized_subprocess_environment(base_env)
        assert "AWS_DEFAULT_REGION" not in result
        assert "AZURE_TENANT_ID" not in result
        assert "GCP_CREDENTIALS" not in result


class TestIntegrationScenarios:
    """Integration-style tests for common scenarios."""

    def test_typical_ci_environment(self) -> None:
        """Test sanitization of a typical CI environment."""
        ci_env = {
            # Essential
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/home/runner",
            "USER": "runner",
            "SHELL": "/bin/bash",
            # Sensitive (should be removed)
            "GITHUB_TOKEN": "ghs_xxx",
            "AWS_ACCESS_KEY_ID": "AKIAxxx",
            "AWS_SECRET_ACCESS_KEY": "xxx",
            "DOCKER_PASSWORD": "secret",
            # Python (should be removed)
            "PYTHONPATH": "/opt/python/libs",
            "PYTHON_VERSION": "3.12.0",
            # Other (should be removed)
            "CI": "true",
            "GITHUB_ACTIONS": "true",
        }
        result = build_sanitized_subprocess_environment(ci_env)
        # Essential vars present
        assert "PATH" in result
        assert "HOME" in result
        # Sensitive vars removed
        assert "GITHUB_TOKEN" not in result
        assert "AWS_ACCESS_KEY_ID" not in result
        assert "AWS_SECRET_ACCESS_KEY" not in result
        assert "DOCKER_PASSWORD" not in result
        # Python vars removed
        assert "PYTHONPATH" not in result
        assert "PYTHON_VERSION" not in result
        # Other non-essential removed
        assert "CI" not in result
        assert "GITHUB_ACTIONS" not in result

    def test_development_environment_with_allow_extra(self) -> None:
        """Test allowing extra vars in a dev environment."""
        dev_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/dev",
            "NODE_ENV": "development",
            "API_KEY": "dev_key",
        }
        result = build_sanitized_subprocess_environment(
            dev_env,
            allow_extra={"NODE_ENV": "development"},
        )
        assert "PATH" in result
        assert "HOME" in result
        assert "NODE_ENV" in result
        assert "API_KEY" not in result

    def test_macos_malloc_debugging_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that macOS malloc debugging vars are stripped."""
        macos_env = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "MallocStackLogging": "1",
            "MallocStackLoggingNoCompact": "1",
        }
        monkeypatch.setattr(sys, "platform", "darwin")
        result = build_sanitized_subprocess_environment(macos_env)
        assert "MallocStackLogging" not in result
        assert "MallocStackLoggingNoCompact" not in result

    def test_allow_extra_overrides_sensitive_in_base(self) -> None:
        """Test that allow_extra can add a sensitive var even if base had it."""
        base_env = {
            "PATH": "/usr/bin",
            "GITHUB_TOKEN": "old_token",  # Will be removed from base
        }
        allow_extra = {"GITHUB_TOKEN": "new_token"}  # But added back via allow_extra
        result = build_sanitized_subprocess_environment(base_env, allow_extra=allow_extra)
        assert result["GITHUB_TOKEN"] == "new_token"


class TestEssentialEnvSelector:
    """Tests for the _essential_env() platform-selection helper."""

    pytestmark = pytest.mark.windows_ci

    def test_posix_set_returned_for_linux(self) -> None:
        """Linux platform should return the POSIX frozenset."""
        assert _essential_env("linux") is _ESSENTIAL_ENV_POSIX

    def test_posix_set_returned_for_darwin(self) -> None:
        """Darwin platform should return the POSIX frozenset."""
        assert _essential_env("darwin") is _ESSENTIAL_ENV_POSIX

    def test_windows_set_returned_for_win32(self) -> None:
        """win32 platform should return the Windows frozenset."""
        assert _essential_env("win32") is _ESSENTIAL_ENV_WINDOWS

    def test_windows_set_contains_critical_vars(self) -> None:
        """Windows set must include the vars that prevent DLL/config failures."""
        required = {
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "APPDATA",
            "LOCALAPPDATA",
            "USERPROFILE",
            "PATHEXT",
            "COMSPEC",
        }
        assert required <= _ESSENTIAL_ENV_WINDOWS

    def test_defaults_to_sys_platform(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without an argument, _essential_env() consults sys.platform."""
        monkeypatch.setattr(sys, "platform", "win32")
        assert _essential_env() is _ESSENTIAL_ENV_WINDOWS

        monkeypatch.setattr(sys, "platform", "linux")
        assert _essential_env() is _ESSENTIAL_ENV_POSIX


class TestBuildSanitizedWindowsPlatform:
    """Tests for build_sanitized_subprocess_environment on Windows platform."""

    pytestmark = pytest.mark.windows_ci

    def _windows_env(self) -> dict[str, str]:
        """Return a representative Windows environment dict."""
        return {
            "PATH": "C:\\Windows\\System32;C:\\Windows",
            "PATHEXT": ".COM;.EXE;.BAT;.CMD",
            "SYSTEMROOT": "C:\\Windows",
            "WINDIR": "C:\\Windows",
            "COMSPEC": "C:\\Windows\\System32\\cmd.exe",
            "TEMP": "C:\\Users\\User\\AppData\\Local\\Temp",
            "TMP": "C:\\Users\\User\\AppData\\Local\\Temp",
            "USERPROFILE": "C:\\Users\\User",
            "HOMEDRIVE": "C:",
            "HOMEPATH": "\\Users\\User",
            "APPDATA": "C:\\Users\\User\\AppData\\Roaming",
            "LOCALAPPDATA": "C:\\Users\\User\\AppData\\Local",
            "PROGRAMFILES": "C:\\Program Files",
            "PROGRAMFILES(X86)": "C:\\Program Files (x86)",
            "PROGRAMDATA": "C:\\ProgramData",
            "USERNAME": "User",
            "COMPUTERNAME": "MYPC",
            "USERDOMAIN": "MYPC",
            "LANG": "en_US.UTF-8",
            "ANTHROPIC_API_KEY": "sk-ant-xxx",
        }

    def test_windows_essential_vars_preserved(self) -> None:
        """All Windows essential vars present in the env must be kept."""
        base_env = self._windows_env()
        result = build_sanitized_subprocess_environment(base_env, platform_name="win32")
        for key in _ESSENTIAL_ENV_WINDOWS:
            if key in base_env:
                assert key in result, f"Expected Windows essential var {key!r} in result"
                assert result[key] == base_env[key]

    def test_sensitive_var_stripped_on_windows(self) -> None:
        """Sensitive credentials must still be stripped even on Windows platform."""
        base_env = self._windows_env()
        result = build_sanitized_subprocess_environment(base_env, platform_name="win32")
        assert "ANTHROPIC_API_KEY" not in result

    def test_linux_platform_drops_windows_vars(self) -> None:
        """When platform_name='linux', Windows-specific vars are not carried over."""
        base_env = self._windows_env()
        result = build_sanitized_subprocess_environment(base_env, platform_name="linux")
        # Windows-only vars must be absent
        for win_var in ("SYSTEMROOT", "APPDATA", "LOCALAPPDATA", "COMSPEC", "WINDIR"):
            assert win_var not in result, f"Windows var {win_var!r} leaked into POSIX result"
        # PATH is in both sets and must be present
        assert "PATH" in result

    def test_allow_extra_works_on_windows_platform(self) -> None:
        """allow_extra must be present alongside Windows essentials."""
        base_env = self._windows_env()
        allow_extra = {"CUSTOM_VAR": "hello"}
        result = build_sanitized_subprocess_environment(
            base_env, allow_extra=allow_extra, platform_name="win32"
        )
        assert result["CUSTOM_VAR"] == "hello"
        assert "SYSTEMROOT" in result
        assert "APPDATA" in result
