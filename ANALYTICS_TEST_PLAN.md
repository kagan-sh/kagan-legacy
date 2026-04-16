# Analytics System Test Plan (Phase 5)

## Overview

Comprehensive test coverage for the multi-dimensional analytics system across all phases (1-5):
- **Phase 1**: Task classification and agent role assignment
- **Phase 2**: Analytics queries and API endpoints
- **Phase 3**: Web UI components
- **Phase 4**: Backend selection integration
- **Phase 5**: Testing and validation

## Test Organization

### Unit Tests

#### `tests/unit/core/test_task_classification.py` (34 tests)
Pure unit tests for the task classification system.

**Test Classes:**
- `TestClassifyTaskIndividual` (20 tests): Individual task classification
  - All task types (CODE_IMPLEMENTATION, BUG_FIX, REFACTORING, TESTING, DOCUMENTATION, OPTIMIZATION, ARCHITECTURE, DESIGN, ANALYSIS, INVESTIGATION, DEPLOYMENT, UNKNOWN)
  - Priority scoring and keyword matching
  - Edge cases (empty input, whitespace, special characters, long text, unicode, URLs)
  - Case insensitivity
  - Multiple keyword handling

- `TestClassifyTasksBatch` (5 tests): Batch classification
  - Multiple task classification
  - Missing fields handling
  - ID preservation

- `TestClassificationEdgeCases` (6 tests): Edge cases
  - Very long text
  - Unicode characters
  - URLs in text
  - Code snippets
  - Markdown formatting
  - Repeated keywords

- `TestClassificationConsistency` (3 tests): Consistency
  - Deterministic behavior
  - Keyword order irrelevance

**Success Criteria:**
- All 34 tests pass
- Classification accuracy > 90%
- No flaky or order-dependent tests

### Core Tests

#### `tests/core/test_analytics.py` (17 tests)
Core analytics functionality tests using the task classification system.

**Test Classes:**
- `TestTaskClassification` (17 tests): Integration of classification system
  - All TaskType categories
  - Classification accuracy
  - Edge cases

**Success Criteria:**
- All 17 tests pass
- Classification matches expected types

#### `tests/core/test_analytics_smoke.py` (10 tests)
Quick smoke tests for rapid validation.

**Test Classes:**
- `TestClassificationSmoke` (10 tests): Basic functionality
  - Function existence and callability
  - Return type validation
  - Determinism
  - Basic classification

**Success Criteria:**
- Runs in < 5 seconds
- All 10 tests pass
- No external dependencies

#### `tests/core/test_analytics_integration.py` (6 integration scenarios)
End-to-end integration tests (Phase 5).

**Test Scenarios:**
1. **Single Task Bug Fix Multiple Attempts**: Task creation → classification → multi-session → analytics
2. **Multiple Task Types Best Backend**: Different task types on different backends
3. **Role-Specific Performance**: Worker vs Reviewer vs Orchestrator performance
4. **3D Analytics**: Comprehensive task type × role × backend aggregation
5. **Failed Sessions**: Success rate calculation with failures
6. **Classification Consistency**: Classification persistence through lifecycle

**Success Criteria:**
- All 6 scenarios pass
- Analytics correctly aggregate across dimensions
- No data loss or inconsistency

### API Tests

#### `tests/server/test_analytics_routes.py` (12 tests)
API endpoint validation (Phase 2).

**Endpoints Tested:**
- `GET /api/analytics/backend-stats`: Backend aggregates
- `GET /api/analytics/by-role`: Role-based grouping
- `GET /api/analytics/by-task-type`: Task type grouping
- `GET /api/analytics/combined`: Full 3D aggregation

**Test Cases:**
- Response structure validation
- Data type correctness
- Enum value validation
- Empty result handling
- Success rate calculation
- Aggregation correctness
- Authentication context

**Success Criteria:**
- All 12 tests pass
- HTTP 200 responses
- Valid JSON structure
- Correct enum values

## Running Tests

### All Analytics Tests
```bash
uv run pytest tests/unit/core/test_task_classification.py \
                tests/core/test_analytics.py \
                tests/core/test_analytics_smoke.py \
                tests/core/test_analytics_integration.py \
                tests/server/test_analytics_routes.py -v
```

### Quick Smoke Test (5 seconds)
```bash
uv run pytest tests/core/test_analytics_smoke.py -v
```

### Classification Tests Only
```bash
uv run pytest tests/unit/core/test_task_classification.py -v
```

### Integration Tests Only
```bash
uv run pytest tests/core/test_analytics_integration.py -v
```

### Server/API Tests Only
```bash
uv run pytest tests/server/test_analytics_routes.py -v
```

## Test Coverage

### Classification System
- **Total Cases**: 34 unit + 17 core + 10 smoke = 61 classification tests
- **Coverage**: 
  - All 12 TaskType enum values
  - Edge cases and special inputs
  - Batch operations
  - Consistency guarantees

### Analytics Queries
- **Tested Query Types**:
  - `backend_stats()`: Per-backend aggregates (count, success_rate, avg_duration, retry_rate)
  - `backend_by_role_stats()`: Backend × role aggregates
  - `backend_by_task_type_stats()`: Backend × task_type aggregates
  - `backend_role_task_stats()`: Full 3D: backend × role × task_type aggregates

- **Coverage**:
  - Empty result handling
  - Single session aggregation
  - Multi-backend comparison
  - Success rate calculation
  - Project ID filtering

### Agent Roles
- **Roles Tested**:
  - WORKER (primary execution role)
  - REVIEWER (review/validation role)
  - ORCHESTRATOR (orchestration role)

- **Coverage**:
  - Role assignment to sessions
  - Role-based analytics grouping
  - Cross-role comparison

### Data Validation
- **Enum Conformance**:
  - TaskType values are valid enum members
  - AgentRole values are valid enum members
  - SessionStatus values are valid enum members

- **Coverage**:
  - Existing data handling
  - New data validation
  - Backfill logic

## Test Scenarios (End-to-End)

### Scenario 1: Bug Fix Workflow
**Setup**: Create a bug fix task
**Flow**: 
1. Task classification (automatic or manual)
2. Create worker session
3. Create reviewer session
4. Check analytics

**Assertions**:
- Task classified as BUG_FIX
- 2 sessions recorded
- 100% success rate
- Both WORKER and REVIEWER roles present

### Scenario 2: Multi-Backend Comparison
**Setup**: Same task, multiple backends
**Flow**:
1. Create task of type CODE_IMPLEMENTATION
2. Run on claude-sonnet (success)
3. Run on claude-opus (failure)
4. Run on claude-haiku (success)

**Assertions**:
- 3 backend entries in stats
- Correct count per backend (1 each)
- Correct success rates
- Best backend recommendation works

### Scenario 3: Role-Specific Metrics
**Setup**: Same task, different roles
**Flow**:
1. Create 3 WORKER sessions
2. Create 2 REVIEWER sessions
3. Create 1 ORCHESTRATOR session

**Assertions**:
- Role counts correct (3, 2, 1)
- All metrics present per role
- Success rates per role correct

### Scenario 4: 3D Analytics
**Setup**: Multiple tasks × multiple backends × multiple roles
**Flow**:
1. Create 3 task types (BUG_FIX, CODE_IMPLEMENTATION, TESTING)
2. Create sessions: each task × 2 backends × 2 roles = 12 sessions
3. Mark all as completed

**Assertions**:
- At least 6 3D result entries (all combinations exist)
- All dimensions represented
- Counts correct per dimension

## Data Validation

### Task Type Validation
- Verify task_type field accepts only valid TaskType enum values
- Test migration: existing tasks without task_type
- Test backfill logic for unclassified tasks

### Agent Role Validation
- Verify agent_role field accepts only valid AgentRole enum values
- Test migration: existing sessions without agent_role
- Test default role assignment

### Session Status Validation
- Verify session status values are valid SessionStatus enum
- Test all status transitions
- Test analytics with mixed statuses

## Success Criteria

### Overall
- [ ] All 61 classification tests pass
- [ ] All 10 smoke tests pass (< 5 sec)
- [ ] All integration tests pass
- [ ] All API tests pass
- [ ] No regressions in existing tests
- [ ] Code coverage > 80% for analytics modules

### Classification
- [ ] Accuracy > 90% on test cases
- [ ] All 12 TaskType values tested
- [ ] Deterministic results
- [ ] Edge cases handled

### Analytics
- [ ] All queries return valid structure
- [ ] Project ID filtering works
- [ ] Success rate calculation correct
- [ ] Aggregation is accurate

### Integration
- [ ] End-to-end workflows succeed
- [ ] Data persists correctly
- [ ] Analytics reflect actual data
- [ ] Multi-dimensional queries work

### API
- [ ] All endpoints return 200
- [ ] Response structure valid
- [ ] Enum values correct
- [ ] Auth context required

## Files Created

```
tests/
├── core/
│   ├── test_analytics.py (17 tests)
│   ├── test_analytics_smoke.py (10 tests)
│   └── test_analytics_integration.py (6 scenarios)
├── unit/
│   └── core/
│       └── test_task_classification.py (34 tests)
└── server/
    └── test_analytics_routes.py (12 tests)
```

## Test Statistics

| Category | Count | Status |
|----------|-------|--------|
| Classification Unit | 34 | PASSING |
| Analytics Core | 17 | PASSING |
| Analytics Smoke | 10 | PASSING |
| Integration | 6 | IMPLEMENTED |
| API Endpoints | 12 | IMPLEMENTED |
| **Total** | **79** | **READY** |

## Maintenance

### Adding New Task Types
1. Add keyword entry to `_TASK_TYPE_KEYWORDS` in `_task_classification.py`
2. Update `TaskType` enum in `core/enums.py`
3. Add test cases to `TestTaskClassification` classes
4. Update smoke tests if needed

### Adding New Analytics Queries
1. Implement query in `Analytics` class in `_analytics.py`
2. Add API route in `_analytics_routes.py`
3. Add test in `test_analytics_routes.py`
4. Update integration tests

### Modifying Classification Algorithm
1. Keep backward compatibility
2. Update test cases if behavior changes
3. Run full test suite
4. Update documentation

## Notes

- Tests use fixtures from `tests/helpers/fixtures.py`
- Task classification is deterministic (no randomness)
- Analytics queries filter by project_id
- All success rates are normalized to [0, 1]
- Duration is in seconds (calculated from julian day difference)
- Empty projects return empty lists (not errors)
