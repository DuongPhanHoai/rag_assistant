from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

TEST_DIR = Path(__file__).resolve().parent.parent

SuiteEvaluator = Callable[[dict[str, Any]], dict[str, Any]]

SUITE_NAMES = ("planning", "sql", "graph", "chart", "kg", "integration")


def suite_cases_path(suite: str) -> Path:
    return TEST_DIR / suite / "cases.json"


def suite_results_path(suite: str) -> Path:
    return TEST_DIR / "results" / f"{suite}_results.jsonl"
