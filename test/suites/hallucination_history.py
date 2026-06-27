"""Hallucination eval history: status matrix + answer log for human review."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval_utils import load_json
from suites.history import format_cell, format_run_column, get_eval_model_name

TEST_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = TEST_DIR / "results"
MANIFEST_PATH = TEST_DIR / "hallucination_cases.json"

HISTORY_CSV = RESULTS_DIR / "hallucination_eval_history.csv"
ANSWERS_CSV = RESULTS_DIR / "hallucination_eval_answers.csv"
RUNS_CSV = RESULTS_DIR / "hallucination_eval_runs.csv"

FIXED_COLUMNS = (
    "registry_id",
    "suite",
    "case_id",
    "hallucination_type",
    "must_not_happen",
)
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
ANSWERS_COLUMNS = (
    "run_column",
    "model",
    "started_at_utc",
    "registry_id",
    "suite",
    "case_id",
    "hallucination_type",
    "must_not_happen",
    "question",
    "status",
    "duration_seconds",
    "auto_failures",
    "review_text",
    "human_verdict",
    "human_notes",
)


@dataclass
class HallucinationHistoryUpdate:
    history_path: Path
    answers_path: Path
    runs_path: Path
    run_column: str
    rows_written: int
    answers_written: int


def load_hallucination_manifest() -> list[dict[str, Any]]:
    return load_json(MANIFEST_PATH)


def extract_review_payload(record: dict[str, Any]) -> str:
    sections: list[str] = []

    answer = record.get("answer")
    if answer:
        sections.append(f"=== ANSWER ===\n{answer}")

    plan = record.get("plan")
    if plan:
        sections.append(f"=== PLAN ===\n{json.dumps(plan, ensure_ascii=False, indent=2)}")

    sql = record.get("sql")
    if sql:
        sections.append(f"=== SQL ===\n{sql}")

    sql_result = record.get("sql_result")
    if isinstance(sql_result, dict) and sql_result.get("rows"):
        sections.append(
            "=== SQL RESULT ===\n"
            f"row_count={sql_result.get('row_count', len(sql_result.get('rows') or []))}\n"
            f"columns={sql_result.get('columns')}"
        )

    artifact = record.get("artifact") or {}
    if artifact.get("markdown"):
        sections.append(f"=== TABLE ARTIFACT ===\n{artifact['markdown']}")
    elif artifact.get("type") == "chart":
        sections.append(f"=== CHART ARTIFACT ===\n{json.dumps(artifact.get('chart_spec'), ensure_ascii=False, indent=2)}")

    graph_artifact = record.get("graph_artifact") or {}
    if graph_artifact.get("markdown"):
        sections.append(f"=== GRAPH ARTIFACT ===\n{graph_artifact['markdown']}")

    sources = record.get("sources")
    if sources:
        sections.append(f"=== SOURCES ===\n{', '.join(sources)}")

    result = record.get("result")
    if isinstance(result, dict):
        nested = extract_review_payload(result)
        if nested and nested != "(no review payload captured)":
            sections.append(nested)

    if not sections and record.get("failures"):
        sections.append(f"=== FAILURES ===\n" + "\n".join(f"- {item}" for item in record["failures"]))

    return "\n\n".join(sections) if sections else "(no review payload captured)"


def _manifest_templates() -> dict[tuple[str, str], dict[str, str]]:
    templates: dict[tuple[str, str], dict[str, str]] = {}
    for entry in load_hallucination_manifest():
        if not entry.get("runnable", True):
            continue
        key = (entry["suite"], entry["case_id"])
        templates[key] = {
            "registry_id": entry.get("registry_id", entry["case_id"]),
            "suite": entry["suite"],
            "case_id": entry["case_id"],
            "hallucination_type": entry.get("hallucination_type", ""),
            "must_not_happen": entry.get("must_not_happen", ""),
        }
    return templates


def _read_history_rows() -> tuple[list[str], dict[tuple[str, str], dict[str, str]]]:
    if not HISTORY_CSV.exists():
        return list(FIXED_COLUMNS), {}

    with HISTORY_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or FIXED_COLUMNS)
        rows: dict[tuple[str, str], dict[str, str]] = {}
        for row in reader:
            key = (row["suite"], row["case_id"])
            rows[key] = {name: row.get(name, "") for name in fieldnames}
        return fieldnames, rows


def append_hallucination_eval_run(
    records: list[dict[str, Any]],
    *,
    model: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    llm_online_mode: bool | None = None,
) -> HallucinationHistoryUpdate:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    model = model or get_eval_model_name()
    started_at = started_at or datetime.now(UTC)
    finished_at = finished_at or datetime.now(UTC)
    run_column = format_run_column(model, started_at)
    started_iso = started_at.astimezone(UTC).isoformat()

    if llm_online_mode is None:
        from student_rag.paths import LLM_ONLINE_MODE

        llm_online_mode = LLM_ONLINE_MODE

    templates = _manifest_templates()
    fieldnames, rows = _read_history_rows()

    for key, template in templates.items():
        rows.setdefault(key, {column: template.get(column, "") for column in FIXED_COLUMNS})
        for column in FIXED_COLUMNS:
            rows[key][column] = template.get(column, rows[key].get(column, ""))

    for record in records:
        key = (str(record.get("suite") or ""), str(record.get("id") or ""))
        template = templates.get(key, {})
        if key not in rows:
            rows[key] = {
                "registry_id": record.get("registry_id") or template.get("registry_id", key[1]),
                "suite": key[0],
                "case_id": key[1],
                "hallucination_type": record.get("hallucination_type")
                or template.get("hallucination_type", ""),
                "must_not_happen": record.get("must_not_happen") or template.get("must_not_happen", ""),
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
            writer.writerow({name: rows[key].get(name, "") for name in fieldnames})

    answers_exists = ANSWERS_CSV.exists()
    answers_written = 0
    with ANSWERS_CSV.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ANSWERS_COLUMNS, extrasaction="ignore")
        if not answers_exists:
            writer.writeheader()
        for record in records:
            key = (str(record.get("suite") or ""), str(record.get("id") or ""))
            template = templates.get(key, {})
            failures = record.get("failures") or []
            writer.writerow(
                {
                    "run_column": run_column,
                    "model": model,
                    "started_at_utc": started_iso,
                    "registry_id": record.get("registry_id") or template.get("registry_id", record.get("id")),
                    "suite": record.get("suite"),
                    "case_id": record.get("id"),
                    "hallucination_type": record.get("hallucination_type")
                    or template.get("hallucination_type", ""),
                    "must_not_happen": record.get("must_not_happen") or template.get("must_not_happen", ""),
                    "question": record.get("question") or "",
                    "status": record.get("status") or "fail",
                    "duration_seconds": str(record.get("duration_seconds") or ""),
                    "auto_failures": " | ".join(failures),
                    "review_text": extract_review_payload(record),
                    "human_verdict": "",
                    "human_notes": "",
                }
            )
            answers_written += 1

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
                "started_at_utc": started_iso,
                "finished_at_utc": finished_at.astimezone(UTC).isoformat(),
                "total_duration_seconds": f"{total_duration:.3f}",
                "passed": str(passed),
                "failed": str(failed),
                "skipped": str(skipped),
                "total_cases": str(len(records)),
                "llm_online_mode": "true" if llm_online_mode else "false",
            }
        )

    return HallucinationHistoryUpdate(
        history_path=HISTORY_CSV,
        answers_path=ANSWERS_CSV,
        runs_path=RUNS_CSV,
        run_column=run_column,
        rows_written=len(ordered_keys),
        answers_written=answers_written,
    )
