"""Run purpose-isolated LLM and pipeline eval cases."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

TEST_DIR = Path(__file__).resolve().parent
ROOT = TEST_DIR.parent
SRC = ROOT / "src"
PURPOSES_DIR = TEST_DIR / "purposes"
RESULTS_PATH = TEST_DIR / "results" / "purpose_results.jsonl"

if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from student_rag.agents.deterministic import (  # noqa: E402
    answer_from_evidence,
    answer_student_question,
    plan_question,
)
from student_rag.data.db import run_sql  # noqa: E402
from student_rag.paths import LLM_ONLINE_MODE  # noqa: E402

from eval_utils import (  # noqa: E402
    append_jsonl,
    check_text_rules,
    discover_purpose_cases,
    new_run_id,
    resolve_fixture_value,
    summarize_case,
    validate_artifact_type,
    validate_plan_flags,
    validate_sources,
    validate_sql_fragments,
    validate_sql_safety,
)


def evaluate_plan_layer(case: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    expected = case.get("expected", {})

    try:
        plan = plan_question(case["question"])
    except Exception as exc:
        failures.append(f"plan_question raised: {exc}")
        return summarize_case(case["id"], failures) | {"layer": "plan", "plan": None}

    failures.extend(validate_plan_flags(plan, expected))

    sql = (plan.get("sql") or "").strip()
    if expected.get("needs_sql"):
        failures.extend(validate_sql_safety(sql))
        failures.extend(validate_sql_fragments(sql, case.get("sql_must_contain")))
        if case.get("sql_must_execute", True):
            try:
                result = run_sql(sql)
                if not result.get("rows"):
                    failures.append("SQL executed but returned zero rows")
            except Exception as exc:
                failures.append(f"SQL execution failed: {exc}")

    return summarize_case(case["id"], failures) | {
        "layer": "plan",
        "purpose": case.get("purpose"),
        "question": case["question"],
        "plan": plan,
    }


def evaluate_answer_layer(case: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    fixtures = case["fixtures"]
    plan = fixtures["plan"]
    sql_result = resolve_fixture_value(fixtures.get("sql_result"))
    graph_context = resolve_fixture_value(fixtures.get("graph_context"))
    artifact = resolve_fixture_value(fixtures["artifact"])

    try:
        answer, used_llm_answer = answer_from_evidence(
            case["question"],
            plan,
            sql_result,
            graph_context,
            artifact,
        )
    except Exception as exc:
        failures.append(f"answer_from_evidence raised: {exc}")
        return summarize_case(case["id"], failures) | {
            "layer": "answer",
            "purpose": case.get("purpose"),
            "answer": None,
        }

    if not used_llm_answer:
        failures.append("answer_from_evidence did not use the LLM")

    failures.extend(
        check_text_rules(
            answer,
            must_include=case.get("must_include"),
            must_not_include=case.get("must_not_include"),
            any_of=case.get("any_of"),
        )
    )

    return summarize_case(case["id"], failures) | {
        "layer": "answer",
        "purpose": case.get("purpose"),
        "question": case["question"],
        "answer": answer,
    }


def evaluate_pipeline_or_e2e(case: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    expected = case.get("expected", {})

    try:
        result = answer_student_question(case["question"])
    except Exception as exc:
        failures.append(f"answer_student_question raised: {exc}")
        return summarize_case(case["id"], failures) | {
            "layer": case.get("layer"),
            "purpose": case.get("purpose"),
        }

    plan = result.get("plan") or {}
    failures.extend(validate_plan_flags(plan, expected))
    failures.extend(validate_artifact_type(result.get("artifact"), expected.get("artifact_type")))
    failures.extend(validate_sources(result.get("sources"), case.get("expected_sources")))

    sql = (plan.get("sql") or "").strip()
    if expected.get("needs_sql"):
        failures.extend(validate_sql_fragments(sql, case.get("sql_must_contain")))
        sql_result = result.get("sql_result") or {}
        if case.get("sql_must_execute", True) and sql_result.get("error"):
            failures.append(f"SQL execution failed: {sql_result['error']}")

    answer = result.get("answer") or ""
    failures.extend(
        check_text_rules(
            answer,
            must_include=case.get("must_include"),
            must_not_include=case.get("must_not_include"),
            any_of=case.get("any_of"),
        )
    )

    return summarize_case(case["id"], failures) | {
        "layer": case.get("layer"),
        "purpose": case.get("purpose"),
        "question": case["question"],
        "plan": plan,
        "artifact_type": (result.get("artifact") or {}).get("type"),
        "sources": result.get("sources"),
        "answer_preview": answer.replace("\n", " ")[:240],
    }


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    layer = case.get("layer", "e2e")
    if layer == "plan":
        return evaluate_plan_layer(case)
    if layer == "answer":
        return evaluate_answer_layer(case)
    if layer in {"pipeline", "e2e"}:
        return evaluate_pipeline_or_e2e(case)
    raise ValueError(f"Unknown layer: {layer}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run purpose-isolated student-agent eval cases.")
    parser.add_argument(
        "--purpose",
        help="Filter by purpose folder prefix, e.g. 01_planning or planning",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available purpose folders and case counts",
    )
    args = parser.parse_args()

    if args.list:
        for cases_path in sorted(PURPOSES_DIR.glob("*/cases.json")):
            cases = discover_purpose_cases(PURPOSES_DIR, cases_path.parent.name)
            print(f"{cases_path.parent.name}: {len(cases)} case(s)")
        return 0

    if not LLM_ONLINE_MODE:
        print("LLM_ONLINE_MODE must be true for purpose eval.")
        return 1

    cases = discover_purpose_cases(PURPOSES_DIR, args.purpose)
    if not cases:
        print("No cases found.")
        return 1

    run_id = new_run_id()
    passed = 0
    failed = 0
    current_purpose = None

    print(f"Running purpose eval ({len(cases)} cases)")
    if args.purpose:
        print(f"Filter: {args.purpose}")
    print(f"Results: {RESULTS_PATH}\n")

    for case in cases:
        if case.get("purpose") != current_purpose:
            current_purpose = case.get("purpose")
            print(f"\n== {current_purpose} ==")

        record = evaluate_case(case)
        record["run_id"] = run_id
        append_jsonl(RESULTS_PATH, record)

        status = record["status"].upper()
        print(f"[{status}] {record['id']} ({record.get('layer')})")
        for failure in record["failures"]:
            print(f"  - {failure}")

        if record["status"] == "pass":
            passed += 1
        else:
            failed += 1

    print(f"\nPurpose eval complete: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    os.chdir(ROOT)
    raise SystemExit(main())
