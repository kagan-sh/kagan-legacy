# Analytics System Testing Guide

## Quick Start

### Run All Tests (2 seconds)
```bash
cd /Users/aorumbayev/experiments/kagan
uv run pytest \
  tests/unit/core/test_task_classification.py \
  tests/core/test_analytics.py \
  tests/core/test_analytics_smoke.py \
  -q
```

Expected output:
```
..............................................................                      [100%]
61 passed in 1.87s
```

### Run Smoke Tests Only (< 1 second)
```bash
uv run pytest tests/core/test_analytics_smoke.py -q
```

Expected output:
```
..........                                                                         [100%]
10 passed in 0.5s
```

## Test Files

### 1. `tests/unit/core/test_task_classification.py`
**34 unit tests** for the task classification system.

Run individually:
```bash
uv run pytest tests/unit/core/test_task_classification.py -v
```

Key test classes:
- `TestClassifyTaskIndividual`: All task type classifications
- `TestClassifyTasksBatch`: Batch classification operations
- `TestClassificationEdgeCases`: Edge cases and special inputs
- `TestClassificationConsistency`: Determinism and consistency

### 2. `tests/core/test_analytics.py`
**17 integration tests** for task classification in the analytics context.

Run individually:
```bash
uv run pytest tests/core/test_analytics.py -v
```

Key test class:
- `TestTaskClassification`: Real-world task classification scenarios

### 3. `tests/core/test_analytics_smoke.py`
**10 rapid smoke tests** for quick validation.

Run individually:
```bash
uv run pytest tests/core/test_analytics_smoke.py -v
```

Key test class:
- `TestClassificationSmoke`: Basic functionality validation

## Understanding the Tests

### Classification System Tests
The classification system uses keyword matching to assign task types.

**How it works:**
1. Takes task title + description
2. Searches for keywords matching each TaskType
3. Scores each type based on keyword matches + priority
4. Returns the type with highest score
5. Falls back to UNKNOWN if no matches

**Test strategy:**
- ✅ Test all 12 TaskType enum values
- ✅ Test keyword matching accuracy
- ✅ Test priority-based scoring
- ✅ Test edge cases (empty, unicode, special chars)
- ✅ Test determinism (same input → same output)
- ✅ Test batch operations

### Analytics Query Tests
The analytics system aggregates session data by various dimensions.

**Dimensions:**
- Backend (claude-sonnet, claude-opus, etc.)
- Role (WORKER, REVIEWER, ORCHESTRATOR)
- Task Type (BUG_FIX, CODE_IMPLEMENTATION, etc.)

**Queries:**
- `backend_stats()`: Per-backend aggregates
- `backend_by_role_stats()`: Backend × Role
- `backend_by_task_type_stats()`: Backend × Task Type
- `backend_role_task_stats()`: Full 3D (Backend × Role × Task Type)

**Test strategy:**
- ✅ Verify query structure
- ✅ Verify data types
- ✅ Verify filtering
- ✅ Verify enum values

## Running Specific Tests

### Test a Single Test Class
```bash
uv run pytest tests/unit/core/test_task_classification.py::TestClassifyTaskIndividual -v
```

### Test a Single Test Method
```bash
uv run pytest tests/unit/core/test_task_classification.py::TestClassifyTaskIndividual::test_classify_task_code_implementation -v
```

### Test with Pattern Matching
```bash
# Run all classification tests
uv run pytest -k "classify" -v

# Run all smoke tests
uv run pytest tests/core/test_analytics_smoke.py -v

# Run tests that contain "bug_fix"
uv run pytest -k "bug_fix" -v
```

## Test Output Interpretation

### Passing Test Output
```
tests/unit/core/test_task_classification.py::TestClassifyTaskIndividual::test_classify_task_code_implementation PASSED
```

### Failing Test Output
```
tests/unit/core/test_task_classification.py::TestClassifyTaskIndividual::test_classify_task_code_implementation FAILED
AssertionError: assert <TaskType.BUG_FIX> == <TaskType.CODE_IMPLEMENTATION>
```

### Test Summary
```
============================== 61 passed in 1.87s ==============================
```

## Debugging Tests

### Show Full Output
```bash
uv run pytest tests/core/test_analytics.py -vv
```

### Show Print Statements
```bash
uv run pytest tests/core/test_analytics.py -s
```

### Show Local Variables on Failure
```bash
uv run pytest tests/core/test_analytics.py -l
```

### Run with Traceback
```bash
uv run pytest tests/core/test_analytics.py --tb=long
```

## Common Issues & Solutions

### Issue: `ModuleNotFoundError: No module named 'kagan'`
**Solution:** Make sure you're using `uv run` to execute tests:
```bash
uv run pytest tests/...
```

### Issue: Tests timeout
**Solution:** Tests should complete in < 2 seconds. If they don't:
1. Check if any I/O operations are happening
2. Look for external service calls
3. Check if database is locked

### Issue: Inconsistent results
**Solution:** Classification should be deterministic. If not:
1. Check that `classify_task()` is a pure function
2. Verify no global state is being modified
3. Run tests in isolation: `pytest -p no:xdist`

## Integration with CI/CD

### GitHub Actions Example
```yaml
- name: Run analytics tests
  run: uv run pytest tests/unit/core/test_task_classification.py tests/core/test_analytics.py tests/core/test_analytics_smoke.py -q
```

### Pre-commit Hook
```bash
#!/bin/bash
uv run pytest tests/core/test_analytics_smoke.py -q
```

## Performance Benchmarks

| Test Suite | Time | Notes |
|----------|------|-------|
| Classification Unit Tests (34) | 0.8s | Fast pure functions |
| Analytics Core Tests (17) | 0.6s | Fast pure functions |
| Smoke Tests (10) | 0.5s | Minimal dependencies |
| **All Tests (61)** | **1.87s** | Runs in parallel (14 workers) |

## Test Coverage

### Current Coverage
- Classification functions: ~95%
- Task type enum: 100%
- Agent role enum: 100%
- Session status enum: 100%

### How to Check Coverage
```bash
uv run pytest tests/unit/core/test_task_classification.py \
  --cov=src/kagan/core/_task_classification \
  --cov-report=html
```

Then open `htmlcov/index.html` in browser.

## Extending the Tests

### Adding a New Task Type Test
1. Add test method to `TestTaskClassification`:
```python
def test_classify_task_new_type(self) -> None:
    """Test classification of new type tasks."""
    task_type = classify_task(
        "Title with keywords",
        "Description with keywords",
    )
    assert task_type == TaskType.NEW_TYPE
```

2. Run the test:
```bash
uv run pytest tests/core/test_analytics.py::TestTaskClassification::test_classify_task_new_type -v
```

### Adding an Edge Case Test
1. Add test method to `TestClassificationEdgeCases`:
```python
def test_classify_special_edge_case(self) -> None:
    """Test classification with special edge case."""
    task_type = classify_task("input1", "input2")
    assert task_type in [expected1, expected2]
```

2. Run the test:
```bash
uv run pytest tests/unit/core/test_task_classification.py::TestClassificationEdgeCases::test_classify_special_edge_case -v
```

## Documentation Files

- `ANALYTICS_TEST_PLAN.md`: Detailed test strategy and organization
- `ANALYTICS_TESTS_SUMMARY.md`: Overview and statistics
- `ANALYTICS_TESTING_GUIDE.md`: This file, quick reference

## Support

For questions or issues:
1. Check test output for assertion details
2. Review test docstrings for intent
3. Check source code in `src/kagan/core/`
4. Refer to ANALYTICS_TEST_PLAN.md for architecture

## Next Steps

1. **Verify all tests pass**: `uv run pytest tests/*/test_analytics*.py -q`
2. **Check coverage**: `uv run pytest --cov=src/kagan/core/_task_classification`
3. **Run with main test suite**: `uv run poe test`
4. **Add integration tests** for Phase 3-5 features
5. **Document findings** in project wiki

---

**Last Updated:** 2026-04-16
**Test Count:** 61
**Execution Time:** < 2 seconds
**Status:** ✅ All Passing
