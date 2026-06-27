"""Shared test runner: list cases, filter by id/layer, run suites."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval_utils import append_jsonl, case_requires_llm, load_cases, load_json, new_run_id
from suites.evaluators import EVALUATORS
from suites.registry import SUITE_NAMES, suite_cases_path, suite_results_path

TEST_DIR = Path(__file__).resolve().parent.parent
HALLUCINATION_MANIFEST = TEST_DIR / "hallucination_cases.json"


@dataclass
class EvalRunSummary:
    run_id: str
    started_at: datetime
    finished_at: datetime
    records: list[dict[str, Any]]
    passed: int
    failed: int
    skipped: int

    @property
    def exit_code(self) -> int:
        return 0 if self.failed == 0 else 1


def load_suite_cases(suite: str) -> list[dict[str, Any]]:
    path = suite_cases_path(suite)
    if not path.exists():
        raise FileNotFoundError(f"No cases file for suite '{suite}': {path}")
    cases = load_cases(path)
    for case in cases:
        case["_suite"] = suite
    return cases


def load_all_cases(suites: list[str] | None = None) -> list[dict[str, Any]]:
    selected = suites or list(SUITE_NAMES)
    cases: list[dict[str, Any]] = []
    for suite in selected:
        cases.extend(load_suite_cases(suite))
    return cases


def filter_cases(
    cases: list[dict[str, Any]],
    *,
    case_id: str | None = None,
    layer: str | None = None,
    no_llm_only: bool = False,
) -> list[dict[str, Any]]:
    filtered = cases
    if case_id:
        filtered = [case for case in filtered if case["id"] == case_id]
    if layer:
        filtered = [case for case in filtered if case.get("layer") == layer]
    if no_llm_only:
        filtered = [case for case in filtered if not case_requires_llm(case)]
    return filtered


def list_cases(suites: list[str] | None = None) -> None:
    for suite in suites or SUITE_NAMES:
        path = suite_cases_path(suite)
        if not path.exists():
            print(f"[{suite}] (missing {path.name})")
            continue
        cases = load_suite_cases(suite)
        print(f"[{suite}] {len(cases)} cases — {path}")
        for case in cases:
            llm = "LLM" if case_requires_llm(case) else "no-LLM"
            layer = case.get("layer") or "-"
            print(f"  {case['id']:<32} layer={layer:<14} {llm}")
        print()


def execute_cases(
    *,
    suites: list[str] | None = None,
    case_id: str | None = None,
    layer: str | None = None,
    no_llm_only: bool = False,
    verbose: bool = True,
) -> EvalRunSummary | None:
    selected_suites = suites or list(SUITE_NAMES)
    if case_id and not suites:
        selected_suites = list(SUITE_NAMES)

    all_cases = load_all_cases(selected_suites)
    cases = filter_cases(all_cases, case_id=case_id, layer=layer, no_llm_only=no_llm_only)

    if case_id and not cases:
        if verbose:
            print(f"No case found with id '{case_id}' in suite(s): {', '.join(selected_suites)}")
        return None

    if not cases:
        if verbose:
            print("No cases matched the current filters.")
        return None

    started_at = datetime.now(UTC)
    run_id = new_run_id()
    passed = failed = skipped = 0
    records: list[dict[str, Any]] = []

    if verbose:
        filters = []
        if case_id:
            filters.append(f"case={case_id}")
        if layer:
            filters.append(f"layer={layer}")
        if no_llm_only:
            filters.append("no-llm-only")
        filter_text = f" ({', '.join(filters)})" if filters else ""
        print(f"Running {len(cases)} case(s){filter_text}")
        print(f"Run id: {run_id}\n")

    for case in cases:
        suite = case["_suite"]
        evaluator = EVALUATORS[suite]
        case_started = time.perf_counter()
        record = evaluator(case)
        record["duration_seconds"] = round(time.perf_counter() - case_started, 3)
        record["run_id"] = run_id
        record["suite"] = suite
        append_jsonl(suite_results_path(suite), record)
        records.append(record)

        status = record["status"]
        if verbose:
            duration = record["duration_seconds"]
            print(f"[{status.upper():4}] {suite}/{record['id']} ({duration:.1f}s)")
            for failure in record.get("failures") or []:
                if status != "skip" or "Skipped:" not in failure:
                    print(f"  - {failure}")

        if status == "pass":
            passed += 1
        elif status == "skip":
            skipped += 1
        else:
            failed += 1

    finished_at = datetime.now(UTC)
    if verbose:
        total_duration = sum(float(record.get("duration_seconds") or 0) for record in records)
        print(f"\nComplete: {passed} passed, {failed} failed, {skipped} skipped ({total_duration:.1f}s total)")
        touched = sorted({case["_suite"] for case in cases})
        for suite in touched:
            print(f"  {suite}: {suite_results_path(suite)}")

    return EvalRunSummary(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        records=records,
        passed=passed,
        failed=failed,
        skipped=skipped,
    )


def run_cases(
    *,
    suites: list[str] | None = None,
    case_id: str | None = None,
    layer: str | None = None,
    no_llm_only: bool = False,
    verbose: bool = True,
) -> int:
    summary = execute_cases(
        suites=suites,
        case_id=case_id,
        layer=layer,
        no_llm_only=no_llm_only,
        verbose=verbose,
    )
    if summary is None:
        return 1
    return summary.exit_code


def load_hallucination_cases() -> list[dict[str, Any]]:
    manifest = load_json(HALLUCINATION_MANIFEST)
    cases_by_key = {(case["_suite"], case["id"]): case for case in load_all_cases()}
    selected: list[dict[str, Any]] = []
    missing: list[str] = []

    for entry in manifest:
        if not entry.get("runnable", True):
            continue
        key = (entry["suite"], entry["case_id"])
        if key not in cases_by_key:
            missing.append(f"{entry['suite']}/{entry['case_id']}")
            continue
        case = dict(cases_by_key[key])
        case["registry_id"] = entry.get("registry_id", entry["case_id"])
        case["hallucination_type"] = entry.get("hallucination_type", "")
        case["must_not_happen"] = entry.get("must_not_happen", "")
        selected.append(case)

    return selected, missing


def execute_hallucination_cases(*, verbose: bool = True) -> EvalRunSummary | None:
    cases, missing = load_hallucination_cases()
    if missing and verbose:
        print(f"Skipping {len(missing)} manifest entries not yet in cases.json:")
        for item in missing:
            print(f"  - {item}")
        print()

    if not cases:
        if verbose:
            print("No runnable hallucination cases found.")
        return None

    started_at = datetime.now(UTC)
    run_id = new_run_id()
    passed = failed = skipped = 0
    records: list[dict[str, Any]] = []

    if verbose:
        print(f"Hallucination eval — {len(cases)} case(s)")
        print(f"Run id: {run_id}\n")

    for case in cases:
        suite = case["_suite"]
        evaluator = EVALUATORS[suite]
        case_started = time.perf_counter()
        record = evaluator(case)
        record["duration_seconds"] = round(time.perf_counter() - case_started, 3)
        record["run_id"] = run_id
        record["suite"] = suite
        record["registry_id"] = case.get("registry_id")
        record["hallucination_type"] = case.get("hallucination_type")
        record["must_not_happen"] = case.get("must_not_happen")
        append_jsonl(suite_results_path(suite), record)
        records.append(record)

        status = record["status"]
        if verbose:
            duration = record["duration_seconds"]
            print(f"[{status.upper():4}] {suite}/{record['id']} ({duration:.1f}s)")
            for failure in record.get("failures") or []:
                if status != "skip" or "Skipped:" not in failure:
                    print(f"  - {failure}")

        if status == "pass":
            passed += 1
        elif status == "skip":
            skipped += 1
        else:
            failed += 1

    finished_at = datetime.now(UTC)
    if verbose:
        total_duration = sum(float(record.get("duration_seconds") or 0) for record in records)
        print(f"\nComplete: {passed} passed, {failed} failed, {skipped} skipped ({total_duration:.1f}s total)")

    return EvalRunSummary(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        records=records,
        passed=passed,
        failed=failed,
        skipped=skipped,
    )


def run_hallucination_eval(verbose: bool = True) -> int:
    from student_rag.paths import LLM_ONLINE_MODE

    from suites.hallucination_history import append_hallucination_eval_run
    from suites.history import get_eval_model_name

    model = get_eval_model_name()
    if verbose:
        print("Hallucination evaluation run")
        print(f"Model: {model}")
        print(f"LLM_ONLINE_MODE: {LLM_ONLINE_MODE}\n")

    summary = execute_hallucination_cases(verbose=verbose)
    if summary is None:
        return 1

    update = append_hallucination_eval_run(
        summary.records,
        model=model,
        started_at=summary.started_at,
        finished_at=summary.finished_at,
        llm_online_mode=LLM_ONLINE_MODE,
    )

    if verbose:
        print(f"\nHistory column added: {update.run_column}")
        print(f"Status matrix: {update.history_path} ({update.rows_written} rows)")
        print(f"Answer log:    {update.answers_path} (+{update.answers_written} rows for human review)")
        print(f"Run log:       {update.runs_path}")
        print("\nFill human_verdict / human_notes in the answer log CSV after reviewing review_text.")

    return summary.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Student Management RAG eval cases one-by-one or by suite.",
    )
    parser.add_argument(
        "--suite",
        action="append",
        dest="suites",
        choices=list(SUITE_NAMES),
        help="Suite to run (repeatable). Default: all suites when --case is omitted.",
    )
    parser.add_argument(
        "--case",
        dest="case_id",
        help="Run a single case by id (searches all suites unless --suite is set).",
    )
    parser.add_argument(
        "--layer",
        help="Filter cases by layer (e.g. sql_only, graph_only, pipeline, e2e).",
    )
    parser.add_argument(
        "--no-llm-only",
        action="store_true",
        help="Run only cases that do not require LLM_ONLINE_MODE.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available cases and exit.",
    )
    parser.add_argument(
        "--model-eval",
        action="store_true",
        help="Run all cases and append results to test/results/model_eval_history.csv.",
    )
    parser.add_argument(
        "--hallucination-eval",
        action="store_true",
        help="Run hallucination registry cases; save status matrix + answer log for human review.",
    )
    return parser


def run_model_eval(verbose: bool = True) -> int:
    from student_rag.paths import LLM_ONLINE_MODE

    from suites.history import append_model_eval_run, get_eval_model_name

    model = get_eval_model_name()
    if verbose:
        print("Model evaluation run — all suites, all cases")
        print(f"Model: {model}")
        print(f"LLM_ONLINE_MODE: {LLM_ONLINE_MODE}\n")

    summary = execute_cases(verbose=verbose)
    if summary is None:
        return 1

    update = append_model_eval_run(
        summary.records,
        model=model,
        started_at=summary.started_at,
        finished_at=summary.finished_at,
        llm_online_mode=LLM_ONLINE_MODE,
    )

    if verbose:
        print(f"\nHistory column added: {update.run_column}")
        print(f"Case matrix: {update.history_path} ({update.rows_written} rows)")
        print(f"Run log:     {update.runs_path}")

    return summary.exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        list_cases(args.suites)
        return 0

    if args.model_eval:
        return run_model_eval()

    if args.hallucination_eval:
        return run_hallucination_eval()

    return run_cases(
        suites=args.suites,
        case_id=args.case_id,
        layer=args.layer,
        no_llm_only=args.no_llm_only,
    )
