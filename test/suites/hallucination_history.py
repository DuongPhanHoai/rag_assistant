"""Hallucination eval history: status matrix + answer log for human review."""

from __future__ import annotations

import csv
import json
import re
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
REVIEWS_DIR = RESULTS_DIR / "hallucination_reviews"

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
    "failure_summary",
    "raw_answer",
    "review_text",
    "human_verdict",
    "human_notes",
)


@dataclass
class HallucinationHistoryUpdate:
    history_path: Path
    answers_path: Path
    runs_path: Path
    reviews_dir: Path
    run_column: str
    rows_written: int
    answers_written: int
    review_markdown_paths: list[Path]


def load_hallucination_manifest() -> list[dict[str, Any]]:
    return load_json(MANIFEST_PATH)


def extract_raw_answer(record: dict[str, Any]) -> str:
    """Primary text a human reads — full LLM answer without truncation."""
    answer = record.get("answer")
    if answer:
        return str(answer).strip()

    nested = record.get("result")
    if isinstance(nested, dict) and nested.get("answer"):
        return str(nested["answer"]).strip()

    plan = record.get("plan")
    if plan and not record.get("answer"):
        layer = record.get("layer") or ""
        if layer == "plan":
            return json.dumps(plan, ensure_ascii=False, indent=2)

    graph_artifact = record.get("graph_artifact") or {}
    if graph_artifact.get("markdown"):
        return str(graph_artifact["markdown"]).strip()

    return ""


def build_failure_summary(record: dict[str, Any]) -> str:
    failures = record.get("failures") or []
    if not failures:
        return ""

    status = record.get("status")
    if status == "skip":
        return "; ".join(failures)

    parts: list[str] = []
    for failure in failures:
        lowered = failure.lower()
        if "missing required phrase" in lowered:
            parts.append(
                f"Automated check: answer did not contain required text ({failure.split(':', 1)[-1].strip()}). "
                "This may mean retrieval returned no evidence, not that the model hallucinated."
            )
        elif "missing expected source" in lowered:
            parts.append(
                f"Automated check: cited sources missing ({failure.split(':', 1)[-1].strip()}). "
                "Graph/SQL may have returned empty evidence."
            )
        elif "must_not_include" in lowered or "forbidden phrase" in lowered:
            parts.append(f"Possible hallucination: {failure}")
        else:
            parts.append(failure)

    plan = record.get("plan") or {}
    if plan.get("needs_graph") and not _has_graph_evidence(record):
        parts.append(
            "Context: planner requested graph lookup but graph evidence appears empty — "
            "model may correctly refuse to invent a threshold."
        )
    if plan.get("needs_sql") and not _has_sql_rows(record):
        parts.append("Context: planner requested SQL but no SQL rows were returned.")

    return " | ".join(parts)


def _has_graph_evidence(record: dict[str, Any]) -> bool:
    graph_artifact = record.get("graph_artifact") or {}
    if graph_artifact.get("path_rows") or graph_artifact.get("risk_rows"):
        return True
    if str(graph_artifact.get("markdown") or "").strip():
        return True
    graph_context = record.get("graph_context") or {}
    if graph_context.get("students") or graph_context.get("topic_matches"):
        return True
    return False


def _has_sql_rows(record: dict[str, Any]) -> bool:
    sql_result = record.get("sql_result") or {}
    return bool(sql_result.get("rows"))


def _should_show_table_artifact(record: dict[str, Any], artifact: dict[str, Any]) -> bool:
    markdown = str(artifact.get("markdown") or "").strip()
    if not markdown or markdown == "No rows returned.":
        plan = record.get("plan") or {}
        if not plan.get("needs_sql", True):
            return False
        if not _has_sql_rows(record):
            return False
    return bool(markdown)


def extract_review_payload(record: dict[str, Any]) -> str:
    sections: list[str] = []

    failures = record.get("failures") or []
    if failures:
        sections.append("=== WHY THIS FAILED (automated) ===\n" + "\n".join(f"- {item}" for item in failures))
        summary = build_failure_summary(record)
        if summary:
            sections.append(f"=== INTERPRETATION ===\n{summary}")

    must_not = record.get("must_not_happen")
    if must_not:
        sections.append(f"=== GUARDRAIL (must not happen) ===\n{must_not}")

    answer = extract_raw_answer(record)
    if answer:
        sections.append(f"=== RAW ANSWER (full text) ===\n{answer}")
    else:
        sections.append("=== RAW ANSWER ===\n(no LLM answer text — deterministic or plan-only case)")

    plan = record.get("plan")
    if plan:
        sections.append(f"=== PLAN ===\n{json.dumps(plan, ensure_ascii=False, indent=2)}")

    sql = record.get("sql")
    if sql:
        sections.append(f"=== SQL ===\n{sql}")

    sql_result = record.get("sql_result")
    if isinstance(sql_result, dict):
        if sql_result.get("error"):
            sections.append(f"=== SQL ERROR ===\n{sql_result['error']}")
        elif sql_result.get("rows"):
            sections.append(
                "=== SQL RESULT ===\n"
                f"row_count={sql_result.get('row_count', len(sql_result.get('rows') or []))}\n"
                f"columns={sql_result.get('columns')}"
            )

    artifact = record.get("artifact") or {}
    if _should_show_table_artifact(record, artifact):
        sections.append(f"=== TABLE ARTIFACT ===\n{artifact['markdown']}")
    elif artifact.get("type") == "chart":
        sections.append(f"=== CHART ARTIFACT ===\n{json.dumps(artifact.get('chart_spec'), ensure_ascii=False, indent=2)}")

    graph_artifact = record.get("graph_artifact") or {}
    graph_markdown = str(graph_artifact.get("markdown") or "").strip()
    if graph_markdown:
        sections.append(f"=== GRAPH EVIDENCE ===\n{graph_markdown}")
    elif plan and plan.get("needs_graph"):
        sections.append(
            "=== GRAPH EVIDENCE ===\n(empty — Neo4j returned no policy paths or topic matches for this query)"
        )
    elif record.get("graph_context") is not None:
        sections.append("=== GRAPH EVIDENCE ===\n(empty)")

    sources = record.get("sources")
    if sources:
        sections.append(f"=== SOURCES ===\n{', '.join(sources)}")
    elif plan and (plan.get("needs_graph") or plan.get("needs_sql")):
        sections.append("=== SOURCES ===\n(none returned)")

    nested = record.get("result")
    if isinstance(nested, dict) and not record.get("answer"):
        nested_payload = extract_review_payload({**record, **nested, "result": None})
        if nested_payload and nested_payload != "(no review payload captured)":
            sections.append(f"=== FULL RUN RESULT ===\n{nested_payload}")

    return "\n\n".join(sections) if sections else "(no review payload captured)"


def _sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^\w\-@.+]", "_", value)
    return cleaned[:140]


def write_review_markdown(
    run_column: str,
    model: str,
    records: list[dict[str, Any]],
) -> list[Path]:
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    path = REVIEWS_DIR / f"{_sanitize_filename(run_column)}.md"

    lines = [
        f"# Hallucination eval — {run_column}",
        "",
        f"- **Model:** `{model}`",
        f"- **Cases:** {len(records)}",
        "",
        "Open this file to read **full raw answers** without CSV column wrapping.",
        "",
        "---",
        "",
    ]

    for record in records:
        case_id = record.get("id") or ""
        suite = record.get("suite") or ""
        status = str(record.get("status") or "fail").upper()
        lines.extend(
            [
                f"## {suite}/{case_id} — {status}",
                "",
                f"**Question:** {record.get('question') or ''}",
                "",
                f"**Hallucination type:** {record.get('hallucination_type') or ''}",
                "",
                f"**Must not happen:** {record.get('must_not_happen') or ''}",
                "",
            ]
        )
        failures = record.get("failures") or []
        if failures:
            lines.append("**Automated failures:**")
            lines.extend(f"- {item}" for item in failures)
            lines.append("")
            summary = build_failure_summary(record)
            if summary:
                lines.extend([f"**Interpretation:** {summary}", ""])

        raw = extract_raw_answer(record)
        lines.extend(
            [
                "### Raw answer",
                "",
                raw if raw else "_(no LLM answer — see evidence in review_text / JSONL)_",
                "",
                "### Full review bundle",
                "",
                "```text",
                extract_review_payload(record),
                "```",
                "",
                "---",
                "",
            ]
        )

    path.write_text("\n".join(lines), encoding="utf-8")
    return [path]


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
            raw_answer = extract_raw_answer(record)
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
                    "failure_summary": build_failure_summary(record),
                    "raw_answer": raw_answer,
                    "review_text": extract_review_payload(record),
                    "human_verdict": "",
                    "human_notes": "",
                }
            )
            answers_written += 1

    review_paths = write_review_markdown(run_column, model, records)

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
        reviews_dir=REVIEWS_DIR,
        run_column=run_column,
        rows_written=len(ordered_keys),
        answers_written=answers_written,
        review_markdown_paths=review_paths,
    )
