from __future__ import annotations

from kagan.core.domain.errors import (
    TASK_NOT_FOUND_CODE,
    task_not_found_message,
    task_not_found_response,
)
from kagan.core.scalars import (
    dict_str_keys_or_none,
    float_or_none,
    int_or_none,
    non_empty_str,
    str_or_none,
    strict_int_or_none,
)


def test_scalar_helpers() -> None:
    assert str_or_none("x") == "x"
    assert str_or_none(1) is None
    assert non_empty_str("  a  ") == "a"
    assert non_empty_str("   ") is None
    assert dict_str_keys_or_none({"a": 1, 2: "b"}) == {"a": 1, "2": "b"}
    assert dict_str_keys_or_none([]) is None
    assert int_or_none("42") == 42
    assert int_or_none(1.5) is None
    assert int_or_none(True) is None
    assert float_or_none(2) == 2.0
    assert float_or_none(" 2.5 ") == 2.5
    assert float_or_none("  ") is None
    assert float_or_none(True) is None
    assert strict_int_or_none(42) == 42
    assert strict_int_or_none("42") is None


def test_task_not_found_helpers() -> None:
    message = task_not_found_message("abc12345")
    assert message == "Task abc12345 not found. Check task_id with task_list."

    payload = task_not_found_response("abc12345")
    assert payload == {
        "success": False,
        "task_id": "abc12345",
        "message": message,
        "code": TASK_NOT_FOUND_CODE,
    }
