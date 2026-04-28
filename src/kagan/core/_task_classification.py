"""Task classification system for analytics and intelligent routing.

Classifies tasks into categories (code implementation, bug fix, refactoring, etc.)
using semantic keywords and patterns in task titles and descriptions.
"""

from kagan.core.enums import TaskType

# Classification keywords for each task type
# These keywords are used to classify tasks based on title and description
_TASK_TYPE_KEYWORDS = {
    TaskType.CODE_IMPLEMENTATION: {
        "keywords": [
            "implement",
            "add feature",
            "create",
            "build",
            "develop",
            "write",
            "new endpoint",
            "api",
            "function",
            "module",
            "feature request",
            "feature",
            "new functionality",
        ],
        "priority": 10,
    },
    TaskType.BUG_FIX: {
        "keywords": [
            "bug",
            "fix",
            "broken",
            "crash",
            "error",
            "exception",
            "failing",
            "not working",
            "issue",
            "regression",
            "defect",
        ],
        "priority": 9,
    },
    TaskType.REFACTORING: {
        "keywords": [
            "refactor",
            "refactoring",
            "cleanup",
            "restructure",
            "reorganize",
            "simplify",
            "reduce duplication",
            "dry",
            "improve readability",
            "technical debt",
            "modernize",
        ],
        "priority": 8,
    },
    TaskType.TESTING: {
        "keywords": [
            "test",
            "testing",
            "unit test",
            "integration test",
            "test coverage",
            "jest",
            "pytest",
            "vitest",
            "mocha",
            "e2e test",
            "automated test",
        ],
        "priority": 7,
    },
    TaskType.OPTIMIZATION: {
        "keywords": [
            "optimize",
            "performance",
            "perf",
            "slow",
            "latency",
            "throughput",
            "memory",
            "caching",
            "cache",
            "speed",
            "efficiency",
            "improve speed",
        ],
        "priority": 6,
    },
    TaskType.DOCUMENTATION: {
        "keywords": [
            "document",
            "docs",
            "readme",
            "comment",
            "jsdoc",
            "docstring",
            "wiki",
            "guide",
            "tutorial",
            "handbook",
        ],
        "priority": 5,
    },
    TaskType.ARCHITECTURE: {
        "keywords": [
            "architecture",
            "design system",
            "structural",
            "component design",
            "system design",
            "schema",
            "scalability",
            "microservice",
            "service",
        ],
        "priority": 4,
    },
    TaskType.DESIGN: {
        "keywords": [
            "design",
            "ux",
            "ui",
            "user experience",
            "interface",
            "styling",
            "layout",
            "component",
            "visual",
        ],
        "priority": 3,
    },
    TaskType.ANALYSIS: {
        "keywords": [
            "analyze",
            "analysis",
            "investigate",
            "research",
            "understand",
            "explore",
            "review code",
            "code review",
            "audit",
            "assessment",
        ],
        "priority": 2,
    },
    TaskType.INVESTIGATION: {
        "keywords": [
            "investigate",
            "debug",
            "troubleshoot",
            "diagnose",
            "root cause",
            "trace",
            "profile",
            "why is",
        ],
        "priority": 2,
    },
    TaskType.DEPLOYMENT: {
        "keywords": [
            "deploy",
            "deployment",
            "release",
            "ci/cd",
            "pipeline",
            "docker",
            "kubernetes",
            "infra",
            "infrastructure",
            "devops",
        ],
        "priority": 4,
    },
}


def classify_task(title: str, description: str = "") -> TaskType:
    """Classify a task into a TaskType based on title and description.

    Uses keyword matching with priority scoring. Returns the best-matching
    TaskType, or TaskType.UNKNOWN if no good match is found.

    Args:
        title: Task title
        description: Task description (optional)

    Returns:
        TaskType enum value representing the inferred task classification
    """
    text = (title + " " + description).lower()

    # Score each task type based on keyword matches
    scores: dict[TaskType, int] = {}

    for task_type, config in _TASK_TYPE_KEYWORDS.items():
        score = 0
        priority = config["priority"]

        # Count keyword matches, giving higher score for more specific matches
        for keyword in config["keywords"]:
            if keyword in text:
                # Give more weight to longer keywords (more specific)
                keyword_weight = len(keyword.split())
                score += priority * keyword_weight

        if score > 0:
            scores[task_type] = score

    # Return the task type with the highest score, or UNKNOWN if no matches
    if not scores:
        return TaskType.UNKNOWN

    best_match = max(scores, key=scores.get)
    return best_match
