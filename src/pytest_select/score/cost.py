"""Static AST-based cost heuristics for tests."""

from __future__ import annotations

import ast

EXPENSIVE_MODULES = frozenset(
    {
        "requests",
        "httpx",
        "urllib",
        "urllib3",
        "boto3",
        "botocore",
        "socket",
        "sqlalchemy",
        "psycopg",
        "psycopg2",
        "asyncpg",
        "django",
        "pymongo",
        "redis",
        "subprocess",
        "multiprocessing",
        "time",
        "asyncio",
        "numpy",
        "pandas",
        "tensorflow",
        "torch",
    }
)

MOCK_NAMES = frozenset({"patch", "MagicMock", "Mock", "mocker", "mock_open"})


def _top_level_module(name: str | None) -> str | None:
    if not name:
        return None
    return name.split(".")[0]


def _is_mocked_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name) and func.id in MOCK_NAMES:
        return True
    if isinstance(func, ast.Attribute) and func.attr in MOCK_NAMES:
        return True
    return False


def score_file_cost(tree: ast.AST) -> float:
    """Higher = more expensive to run (static estimate)."""
    cost = 1.0
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = _top_level_module(node.module)
            if mod in EXPENSIVE_MODULES:
                cost += 5.0
        elif isinstance(node, ast.Import):
            for alias in node.names:
                mod = _top_level_module(alias.name)
                if mod in EXPENSIVE_MODULES:
                    cost += 5.0
        elif isinstance(node, ast.Call):
            if _is_mocked_call(node):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr in ("sleep", "Popen", "run", "execute"):
                    cost += 8.0
            elif isinstance(func, ast.Name):
                if func.id in ("sleep", "open", "system"):
                    cost += 5.0
    return cost
