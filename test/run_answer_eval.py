"""Evaluate LLM step 2: answer_from_evidence()."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from student_rag.agents.deterministic import answer_from_evidence  # noqa: E402
from student_rag.paths import LLM_ONLINE_MODE  # noqa: E402

from eval_utils import (  # noqa: E402
    append_jsonl,
    check_text_rules,
    load_cases,
    load_fixture,
    new_run_id,
    summarize_case,
)


CASES_PATH = TEST_DIR / "llm_answer_cases.json"
RESULTS_PATH = TEST_DIR / "results" / "answer_results.jsonl"


def resolve_fixture_value(value):
    if isinstance(value, str) and value.endswith(".json"):
        return load_fixture(value)
    return value


def evaluate_case(case: dict) -> dict:
    case_id = case["id"]
    question = case["question"]
    fixtures = case["fixtures"]
    failures: list[str] = []

    plan = fixtures["plan"]
    sql_result = resolve_fixture_value(fixtures.get("sql_result"))
    graph_context = resolve_fixture_value(fixtures.get("graph_context"))
    artifact = resolve_fixture_value(fixtures["artifact"])

    try:
        answer, used_llm_answer = answer_from_evidence(
            question,
            plan,
            sql_result,
            graph_context,
            artifact,
        )
    except Exception as exc:
        failures.append(f"answer_from_evidence raised: {exc}")
        return summarize_case(case_id, failures) | {
            "question": question,
            "answer": None,
            "used_llm_answer": False,
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

    return summarize_case(case_id, failures) | {
        "question": question,
        "answer": answer,
        "used_llm_answer": used_llm_answer,
        "fixture_files": {
            key: value
            for key, value in fixtures.items()
            if isinstance(value, str) and value.endswith(".json")
        },
    }


def main() -> int:
    if not LLM_ONLINE_MODE:
        print("LLM_ONLINE_MODE must be true for answer-step eval.")
        return 1

    cases = load_cases(CASES_PATH)
    run_id = new_run_id()
    passed = 0
    failed = 0

    print(f"Running answer-step eval ({len(cases)} cases)")
    print(f"Cases: {CASES_PATH}")
    print(f"Results: {RESULTS_PATH}\n")

    for case in cases:
        record = evaluate_case(case)
        record["run_id"] = run_id
        record["step"] = "answer_from_evidence"
        append_jsonl(RESULTS_PATH, record)

        status = record["status"].upper()
        print(f"[{status}] {record['id']}")
        for failure in record["failures"]:
            print(f"  - {failure}")
        if record.get("answer"):
            preview = record["answer"].replace("\n", " ")[:160]
            print(f"  answer: {preview}...")

        if record["status"] == "pass":
            passed += 1
        else:
            failed += 1

    print(f"\nAnswer eval complete: {passed} passed, {failed} failed")
    print(f"Detailed results: {RESULTS_PATH}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    os.chdir(ROOT)
    raise SystemExit(main())
