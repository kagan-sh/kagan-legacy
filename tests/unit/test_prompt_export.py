"""Unit tests for prompt export to .prompt.yml format."""

from __future__ import annotations

import pytest

from pathlib import Path

from kagan.core._prompt_export import PROMPT_TYPES, export_prompt_text, export_prompt_yml, write_prompt_yml


# Use empty settings dict — prompt resolution works with defaults
_EMPTY_SETTINGS: dict[str, str] = {}


class TestExportPromptYml:
    """Tests for export_prompt_yml()."""

    @pytest.mark.unit
    def test_orchestrator_produces_valid_structure(self) -> None:
        result = export_prompt_yml("orchestrator", _EMPTY_SETTINGS)
        assert "name: kagan-orchestrator" in result
        assert "model: openai/gpt-4.1" in result
        assert "messages:" in result
        assert "role: system" in result
        assert "content: |" in result

    @pytest.mark.unit
    def test_execution_includes_task_fields(self) -> None:
        result = export_prompt_yml("execution", _EMPTY_SETTINGS)
        # Default placeholder task has these
        assert "Example task" in result
        assert "Tests pass" in result

    @pytest.mark.unit
    def test_review_includes_placeholder_task_id(self) -> None:
        result = export_prompt_yml("review", _EMPTY_SETTINGS)
        assert "TASK_ID_PLACEHOLDER" in result

    @pytest.mark.unit
    def test_review_with_explicit_task_id(self) -> None:
        result = export_prompt_yml("review", _EMPTY_SETTINGS, task_id="abc-123")
        assert "abc-123" in result

    @pytest.mark.unit
    def test_all_types_succeed(self) -> None:
        for prompt_type in PROMPT_TYPES:
            result = export_prompt_yml(prompt_type, _EMPTY_SETTINGS)
            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.unit
    def test_custom_model_appears_in_output(self) -> None:
        result = export_prompt_yml(
            "orchestrator", _EMPTY_SETTINGS, model="meta/llama-4-scout-17b-16e-instruct"
        )
        assert "model: meta/llama-4-scout-17b-16e-instruct" in result

    @pytest.mark.unit
    def test_unknown_type_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown prompt type"):
            export_prompt_yml("nonexistent", _EMPTY_SETTINGS)

    @pytest.mark.unit
    def test_with_behavioral_settings(self) -> None:
        settings = {
            "review_strictness": "strict",
            "planning_depth": "always",
        }
        result = export_prompt_yml("orchestrator", settings)
        # Behavioral clauses should be compiled into the prompt
        assert isinstance(result, str)
        assert len(result) > 100


class TestWritePromptYml:
    """Tests for write_prompt_yml()."""

    @pytest.mark.unit
    def test_writes_file(self, tmp_path: Path) -> None:
        content = "name: test\nmodel: test\n"
        dest = tmp_path / "sub" / "test.prompt.yml"
        result = write_prompt_yml(content, dest)
        assert result == dest
        assert dest.read_text() == content

    @pytest.mark.unit
    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        dest = tmp_path / "deep" / "nested" / "dir" / "prompt.yml"
        write_prompt_yml("content", dest)
        assert dest.exists()


class TestExportPromptText:
    """Tests for export_prompt_text()."""

    @pytest.mark.unit
    def test_orchestrator_returns_raw_content(self) -> None:
        result = export_prompt_text("orchestrator", _EMPTY_SETTINGS)
        # Should contain prompt content but NO YAML structure
        assert "name:" not in result
        assert "messages:" not in result
        assert "kagan" in result.lower()

    @pytest.mark.unit
    def test_execution_returns_task_fields(self) -> None:
        result = export_prompt_text("execution", _EMPTY_SETTINGS)
        assert "Example task" in result
        assert "Tests pass" in result

    @pytest.mark.unit
    def test_review_returns_protocol(self) -> None:
        result = export_prompt_text("review", _EMPTY_SETTINGS)
        assert "review-protocol" in result or "Review task" in result

    @pytest.mark.unit
    def test_all_types_return_nonempty_strings(self) -> None:
        for prompt_type in PROMPT_TYPES:
            result = export_prompt_text(prompt_type, _EMPTY_SETTINGS)
            assert isinstance(result, str)
            assert len(result) > 50

    @pytest.mark.unit
    def test_unknown_type_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown prompt type"):
            export_prompt_text("bogus", _EMPTY_SETTINGS)

    @pytest.mark.unit
    def test_model_with_special_chars_is_quoted(self) -> None:
        result = export_prompt_yml("orchestrator", _EMPTY_SETTINGS, model="my-model: v2 # test")
        assert 'model: "my-model: v2 # test"' in result

    @pytest.mark.unit
    def test_text_differs_from_yml(self) -> None:
        text = export_prompt_text("orchestrator", _EMPTY_SETTINGS)
        yml = export_prompt_yml("orchestrator", _EMPTY_SETTINGS)
        # Text should be a substring of the yml (the content portion)
        # but yml has YAML wrapper around it
        assert "name: kagan-orchestrator" not in text
        assert "name: kagan-orchestrator" in yml
