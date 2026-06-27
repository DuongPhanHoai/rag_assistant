"""Append model evaluation runs to a wide-format CSV history matrix."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval_utils import case_requires_llm
from suites.registry import SUITE_NAMES, suite_cases_path

TEST_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = TEST_DIR / "results"
HISTORY_CSV = RESULTS_DIR / "model_eval_history.csv"
RUNS_CSV = RESULTS_DIR / "model_eval_runs.csv"

FIXED_COLUMNS = ("suite", "case_id", "layer", "requires_llm")
RUNS_COLUMNS = (
    "run_column",
    "model",
    "started_at_utc",
    "finished_at_utc",
    "total_duration_seconds",
    "passed",
    "failed",
    "skipped",
    "total_cases",
    "llm_online_mode",
)


@dataclass
class HistoryUpdate:
    history_path: Path
    runs_path: Path
    run_column: str
    rows_written: int


def get_eval_model_name() -> str:
    import os

    return os.getenv("LMSTUDIO_MODEL", "unknown")


def format_run_column(model: str, started_at: datetime) -> str:
    timestamp = started_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"{model} @ {timestamp}"


def format_cell(status: str, duration_seconds: float | None) -> str:
    if duration_seconds is None:
        return status
    return f"{status} ({duration_seconds:.1f}s)"


def _case_row_template(case: dict[str, Any]) -> dict[str, str]:
    return {
        "suite": case["_suite"],
        "case_id": case["id"],
        "layer": str(case.get("layer") or ""),
        "requires_llm": "true" if case_requires_llm(case) else "false",
    }


def load_all_case_templates() -> dict[tuple[str, str], dict[str, str]]:
    from eval_utils import load_cases

    templates: dict[tuple[str, str], dict[str, str]] = {}
    for suite in SUITE_NAMES:
        path = suite_cases_path(suite)
        if not path.exists():
            continue
        for case in load_cases(path):
            case = dict(case)
            case["_suite"] = suite
            key = (suite, case["id"])
            templates[key] = _case_row_template(case)
    return templates


def _read_history_rows() -> tuple[list[str], dict[tuple[str, str], dict[str, str]]]:
    if not HISTORY_CSV.exists():
        return list(FIXED_COLUMNS), {}

    with HISTORY_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or list(FIXED_COLUMNS)
        rows: dict[tuple[str, str], dict[str, str]] = {}
        for row in reader:
            key = (row["suite"], row["case_id"])
            rows[key] = {name: row.get(name, "") for name in fieldnames}
        return fieldnames, rows


def append_model_eval_run(
    records: list[dict[str, Any]],
    *,
    model: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    llm_online_mode: bool | None = None,
) -> HistoryUpdate:
    """Merge one full eval run into the wide history CSV and append run metadata."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    model = model or get_eval_model_name()
    started_at = started_at or datetime.now(UTC)
    finished_at = finished_at or datetime.now(UTC)
    run_column = format_run_column(model, started_at)

    if llm_online_mode is None:
        from student_rag.paths import LLM_ONLINE_MODE

        llm_online_mode = LLM_ONLINE_MODE

    templates = load_all_case_templates()
    fieldnames, rows = _read_history_rows()

    for key, template in templates.items():
        rows.setdefault(key, {column: template.get(column, "") for column in FIXED_COLUMNS})
        for column in FIXED_COLUMNS:
            rows[key][column] = template.get(column, rows[key].get(column, ""))

    for record in records:
        key = (str(record.get("suite") or ""), str(record.get("id") or ""))
        if key not in rows:
            rows[key] = {
                "suite": key[0],
                "case_id": key[1],
                "layer": str(record.get("layer") or ""),
                "requires_llm": "true" if record.get("requires_llm") else "false",
            }
        rows[key][run_column] = format_cell(
            str(record.get("status") or "fail"),
            record.get("duration_seconds"),
        )

    if run_column not in fieldnames:
        fieldnames = [*fieldnames, run_column]

    ordered_keys = sorted(rows.keys(), key=lambda item: (item[0], item[1]))
    with HISTORY_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for key in ordered_keys:
            row = {name: rows[key].get(name, "") for name in fieldnames}
            writer.writerow(row)

    passed = sum(1 for record in records if record.get("status") == "pass")
    failed = sum(1 for record in records if record.get("status") == "fail")
    skipped = sum(1 for record in records if record.get("status") == "skip")
    total_duration = sum(float(record.get("duration_seconds") or 0) for record in records)

    runs_exists = RUNS_CSV.exists()
    with RUNS_CSV.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RUNS_COLUMNS)
        if not runs_exists:
            writer.writeheader()
        writer.writerow(
            {
                "run_column": run_column,
                "model": model,
                "started_at_utc": started_at.astimezone(UTC).isoformat(),
                "finished_at_utc": finished_at.astimezone(UTC).isoformat(),
                "total_duration_seconds": f"{total_duration:.3f}",
                "passed": str(passed),
                "failed": str(failed),
                "skipped": str(skipped),
                "total_cases": str(len(records)),
                "llm_online_mode": "true" if llm_online_mode else "false",
            }
        )

    return HistoryUpdate(
        history_path=HISTORY_CSV,
        runs_path=RUNS_CSV,
        run_column=run_column,
        rows_written=len(ordered_keys),
    )
