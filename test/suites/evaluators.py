"""Per-suite case evaluators."""

from __future__ import annotations

from typing import Any

from student_rag.agents.deterministic import (
    answer_from_evidence,
    answer_student_question,
    generate_table_or_chart_spec,
    get_graph_evidence,
    plan_question,
    replan_if_needed,
)
from student_rag.artifacts import graph_artifact_from_context
from student_rag.data.db import run_sql
from student_rag.paths import LLM_ONLINE_MODE

from eval_utils import (
    case_requires_llm,
    check_text_rules,
    merge_expected,
    resolve_fixture_value,
    summarize_case,
    validate_artifact_type,
    validate_chart_spec,
    validate_graph_warning,
    validate_mode,
    validate_path_rows,
    validate_plan_flags,
    validate_plan_invariants,
    validate_sources_any_of,
    validate_sources_must_contain,
    validate_sql_fragments,
    validate_sql_result,
    validate_sql_safety,
    validate_student_names_in_graph,
)


def _base_record(case: dict[str, Any], failures: list[str]) -> dict[str, Any]:
    record = summarize_case(case["id"], failures)
    record["question"] = case.get("question")
    record["layer"] = case.get("layer")
    record["techniques"] = case.get("techniques")
    record["suite"] = case.get("_suite")
    record["requires_llm"] = case_requires_llm(case)
    return record


def _skip_llm_record(case: dict[str, Any]) -> dict[str, Any]:
    failures = ["Skipped: case requires LLM but LLM_ONLINE_MODE is false"]
    record = _base_record(case, failures)
    record["status"] = "skip"
    record["failure_count"] = 0
    record["failures"] = failures
    return record


def evaluate_planning(case: dict[str, Any]) -> dict[str, Any]:
    if case_requires_llm(case) and not LLM_ONLINE_MODE:
        return _skip_llm_record(case)

    expected = merge_expected(case)
    failures: list[str] = []
    plan: dict[str, Any] | None = None

    try:
        plan = plan_question(case["question"])
    except Exception as exc:
        failures.append(f"plan_question raised: {exc}")
        return _base_record(case, failures) | {"plan": None, "expected": expected}

    failures.extend(validate_plan_flags(plan, expected))
    failures.extend(validate_plan_invariants(plan))
    return _base_record(case, failures) | {"plan": plan, "expected": expected}


def evaluate_sql(case: dict[str, Any]) -> dict[str, Any]:
    layer = case.get("layer", "sql_only")
    expected = merge_expected(case)
    failures: list[str] = []
    sql = case.get("sql")
    plan: dict[str, Any] | None = None
    sql_result: dict[str, Any] | None = None
    artifact: dict[str, Any] | None = None

    if layer == "pipeline":
        if not LLM_ONLINE_MODE:
            return _skip_llm_record(case)
        try:
            plan = plan_question(case["question"])
        except Exception as exc:
            failures.append(f"plan_question raised: {exc}")
            return _base_record(case, failures) | {"plan": None}

        failures.extend(validate_plan_flags(plan, expected))
        sql = plan.get("sql")
    elif not sql:
        failures.append("sql_only case missing sql field")
        return _base_record(case, failures)

    failures.extend(validate_sql_safety(str(sql or "")))
    failures.extend(validate_sql_fragments(str(sql or ""), expected.get("sql_must_contain")))
    if failures:
        if expected.get("expect_validation_failure"):
            failures = []
        return _base_record(case, failures) | {"sql": sql, "plan": plan}

    try:
        sql_result = run_sql(str(sql))
    except Exception as exc:
        failures.append(f"run_sql raised: {exc}")
        return _base_record(case, failures) | {"sql": sql, "plan": plan}

    failures.extend(
        validate_sql_result(
            sql_result,
            min_row_count=expected.get("min_row_count"),
            max_row_count=expected.get("max_row_count"),
            exact_row_count=expected.get("exact_row_count"),
            columns_must_include=expected.get("columns_must_include"),
            row_must_include=expected.get("row_must_include"),
            expect_error=bool(expected.get("expect_sql_error")),
        )
    )

    needs_chart = bool(expected.get("needs_chart", False))
    artifact = generate_table_or_chart_spec(
        question=case.get("question") or "",
        sql_result=sql_result,
        needs_chart=needs_chart,
    )
    failures.extend(validate_artifact_type(artifact, expected.get("artifact_type")))

    if expected.get("expect_validation_failure"):
        if failures:
            failures = []
        else:
            failures.append("Expected validation failure but all checks passed")

    return _base_record(case, failures) | {
        "sql": sql,
        "plan": plan,
        "sql_result": sql_result,
        "artifact": artifact,
    }


def evaluate_graph(case: dict[str, Any]) -> dict[str, Any]:
    expected = merge_expected(case)
    failures: list[str] = []
    question = case["question"]
    graph_query = case.get("graph_query") or question

    try:
        graph_context = get_graph_evidence(question, graph_query)
    except Exception as exc:
        failures.append(f"get_graph_evidence raised: {exc}")
        return _base_record(case, failures)

    graph_artifact = graph_artifact_from_context(graph_context)
    path_rows = graph_artifact.get("path_rows") or []

    failures.extend(validate_graph_warning(graph_context, bool(expected.get("expect_warning"))))
    failures.extend(
        validate_path_rows(
            path_rows,
            expected_paths_exact=expected.get("expected_paths_exact"),
            expected_path_rows=expected.get("expected_path_rows"),
            min_path_count=expected.get("min_path_count"),
        )
    )
    failures.extend(validate_student_names_in_graph(graph_context, expected.get("student_names_must_include")))

    if expected.get("markdown_non_empty") and not str(graph_artifact.get("markdown") or "").strip():
        failures.append("Expected non-empty graph artifact markdown")
    if expected.get("markdown_empty") and str(graph_artifact.get("markdown") or "").strip():
        failures.append("Expected empty graph artifact markdown")

    sources = _collect_sources(graph_context)
    failures.extend(validate_sources_must_contain(sources, expected.get("sources_must_contain")))
    failures.extend(validate_sources_any_of(sources, expected.get("sources_any_of")))

    return _base_record(case, failures) | {
        "graph_context": graph_context,
        "graph_artifact": graph_artifact,
        "sources": sources,
    }


def evaluate_chart(case: dict[str, Any]) -> dict[str, Any]:
    layer = case.get("layer", "artifact_only")
    expected = merge_expected(case)
    failures: list[str] = []
    plan: dict[str, Any] | None = None
    sql_result: dict[str, Any] | None = None

    if layer == "pipeline":
        if not LLM_ONLINE_MODE:
            return _skip_llm_record(case)
        try:
            plan = plan_question(case["question"])
        except Exception as exc:
            failures.append(f"plan_question raised: {exc}")
            return _base_record(case, failures) | {"plan": None}

        failures.extend(validate_plan_flags(plan, expected))
        needs_chart = bool(plan.get("needs_chart"))
        if plan.get("needs_sql") and plan.get("sql"):
            try:
                sql_result = run_sql(plan["sql"])
            except Exception as exc:
                failures.append(f"run_sql raised: {exc}")
        else:
            sql_result = {"rows": [], "columns": []}
    elif layer == "answer":
        if not LLM_ONLINE_MODE:
            return _skip_llm_record(case)
        fixture = resolve_fixture_value(case.get("fixture"))
        graph_context = fixture.get("graph_context")
        sql_result = fixture.get("sql_result") or {"rows": [], "columns": []}
        plan = fixture.get("plan") or {"needs_chart": True, "needs_sql": True, "needs_graph": False}
        needs_chart = bool(plan.get("needs_chart", True))
        artifact = generate_table_or_chart_spec(case["question"], sql_result, needs_chart)
        try:
            answer, used_llm = answer_from_evidence(case["question"], plan, sql_result, graph_context, artifact)
        except Exception as exc:
            failures.append(f"answer_from_evidence raised: {exc}")
            return _base_record(case, failures)
        failures.extend(check_text_rules(answer, **{k: expected.get(k) for k in ("must_include", "must_not_include", "any_of") if expected.get(k)}))
        return _base_record(case, failures) | {"answer": answer, "used_llm_answer": used_llm, "artifact": artifact}
    else:
        fixture = resolve_fixture_value(case.get("fixture"))
        if isinstance(fixture, dict) and "rows" in fixture:
            sql_result = fixture
        else:
            sql_result = fixture.get("sql_result") if isinstance(fixture, dict) else {"rows": [], "columns": []}
        needs_chart = bool(expected.get("needs_chart", True))

    artifact = generate_table_or_chart_spec(
        question=case.get("question") or "",
        sql_result=sql_result or {"rows": [], "columns": []},
        needs_chart=needs_chart if layer != "pipeline" else bool(plan and plan.get("needs_chart")),
    )
    failures.extend(validate_artifact_type(artifact, expected.get("artifact_type")))
    failures.extend(validate_chart_spec(artifact, expected.get("chart")))

    return _base_record(case, failures) | {
        "plan": plan,
        "sql_result": sql_result,
        "artifact": artifact,
    }


def evaluate_kg(case: dict[str, Any]) -> dict[str, Any]:
    layer = case.get("layer", "graph_only")
    expected = merge_expected(case)
    failures: list[str] = []
    question = case["question"]
    graph_query = case.get("graph_query") or question

    if layer == "answer":
        if not LLM_ONLINE_MODE:
            return _skip_llm_record(case)
        fixture = resolve_fixture_value(case.get("fixture"))
        graph_context = fixture.get("graph_context") or fixture
        sql_result = fixture.get("sql_result")
        plan = fixture.get("plan") or {"needs_graph": True, "needs_sql": False, "needs_chart": False}
        artifact = generate_table_or_chart_spec(question, sql_result or {"rows": [], "columns": []}, False)
        try:
            answer, used_llm = answer_from_evidence(question, plan, sql_result, graph_context, artifact)
        except Exception as exc:
            failures.append(f"answer_from_evidence raised: {exc}")
            return _base_record(case, failures)
        failures.extend(check_text_rules(answer, **{k: expected.get(k) for k in ("must_include", "must_not_include", "any_of") if expected.get(k)}))
        sources = _collect_sources(graph_context)
        failures.extend(validate_sources_must_contain(sources, expected.get("sources_must_contain")))
        return _base_record(case, failures) | {"answer": answer, "sources": sources, "used_llm_answer": used_llm}

    if layer == "pipeline":
        if not LLM_ONLINE_MODE:
            return _skip_llm_record(case)
        try:
            result = answer_student_question(question)
        except Exception as exc:
            failures.append(f"answer_student_question raised: {exc}")
            return _base_record(case, failures)
        failures.extend(check_text_rules(result.get("answer") or "", **{k: expected.get(k) for k in ("must_include", "must_not_include", "any_of") if expected.get(k)}))
        failures.extend(validate_sources_must_contain(result.get("sources"), expected.get("sources_must_contain")))
        return _base_record(case, failures) | {
            "answer": result.get("answer"),
            "sources": result.get("sources"),
            "mode": result.get("mode"),
            "plan": result.get("plan"),
            "artifact": result.get("artifact"),
            "graph_artifact": result.get("graph_artifact"),
            "sql_result": result.get("sql_result"),
        }

    try:
        graph_context = get_graph_evidence(question, graph_query)
    except Exception as exc:
        failures.append(f"get_graph_evidence raised: {exc}")
        return _base_record(case, failures)

    graph_artifact = graph_artifact_from_context(graph_context)
    sources = _collect_sources(graph_context)
    failures.extend(validate_sources_must_contain(sources, expected.get("sources_must_contain")))
    failures.extend(validate_sources_any_of(sources, expected.get("sources_any_of")))
    failures.extend(validate_graph_warning(graph_context, bool(expected.get("expect_warning"))))
    failures.extend(validate_student_names_in_graph(graph_context, expected.get("topic_must_include")))

    if expected.get("expect_empty_evidence"):
        has_evidence = bool(graph_context.get("students")) or bool(graph_context.get("topic_matches"))
        if has_evidence and not graph_context.get("warning"):
            failures.append("Expected empty graph evidence but data was returned")

    return _base_record(case, failures) | {
        "graph_context": graph_context,
        "graph_artifact": graph_artifact,
        "sources": sources,
    }


def evaluate_integration(case: dict[str, Any]) -> dict[str, Any]:
    layer = case.get("layer", "e2e")
    expected = merge_expected(case)
    failures: list[str] = []
    case_id = case["id"]

    if layer == "fidelity":
        if not LLM_ONLINE_MODE:
            return _skip_llm_record(case)
        fixture = resolve_fixture_value(case.get("fixture"))
        if isinstance(fixture, dict) and "graph_context" in fixture:
            graph_context = fixture.get("graph_context")
            sql_result = fixture.get("sql_result")
        elif isinstance(fixture, dict) and "students" in fixture:
            graph_context = fixture
            sql_result = None
        else:
            graph_context = None
            sql_result = fixture if isinstance(fixture, dict) else None
        plan = fixture.get("plan") or {}
        needs_chart = bool(plan.get("needs_chart"))
        artifact = generate_table_or_chart_spec(case["question"], sql_result or {"rows": [], "columns": []}, needs_chart)
        try:
            answer, used_llm = answer_from_evidence(case["question"], plan, sql_result, graph_context, artifact)
        except Exception as exc:
            failures.append(f"answer_from_evidence raised: {exc}")
            return _base_record(case, failures)
        failures.extend(check_text_rules(answer, **{k: expected.get(k) for k in ("must_include", "must_not_include", "any_of") if expected.get(k)}))
        return _base_record(case, failures) | {"answer": answer, "used_llm_answer": used_llm}

    if layer == "replan" and case_id == "empty_sql_replan":
        if not LLM_ONLINE_MODE:
            return _skip_llm_record(case)
        question = case["question"]
        try:
            plan = plan_question(question)
        except Exception as exc:
            failures.append(f"plan_question raised: {exc}")
            return _base_record(case, failures)

        first_sql = plan.get("sql")
        empty_result = {"sql": first_sql, "rows": [], "columns": [], "row_count": 0}
        new_plan, new_result = replan_if_needed(question, plan, empty_result, None)
        second_sql = new_plan.get("sql")
        if second_sql == first_sql:
            failures.append("Replan did not change SQL query")
        row_count = int((new_result or {}).get("row_count", 0))
        if row_count <= 0:
            failures.append(f"Replan SQL returned no rows (row_count={row_count})")
        return _base_record(case, failures) | {"first_sql": first_sql, "second_sql": second_sql, "sql_result": new_result}

    if layer == "infra" and case_id in {"offline_mode", "offline_mode_e2e"}:
        if LLM_ONLINE_MODE:
            record = _skip_llm_record(case)
            record["failures"] = ["Skipped: run with LLM_ONLINE_MODE=false for offline_mode"]
            record["status"] = "skip"
            return record
        try:
            result = answer_student_question(case["question"])
        except Exception as exc:
            failures.append(f"answer_student_question raised: {exc}")
            return _base_record(case, failures)
        failures.extend(validate_mode(result.get("mode"), expected.get("mode", "offline_evidence")))
        if expected.get("answer_must_include"):
            failures.extend(check_text_rules(result.get("answer") or "", must_include=expected["answer_must_include"]))
        return _base_record(case, failures) | {"result": result}

    if case_requires_llm(case) and not LLM_ONLINE_MODE:
        return _skip_llm_record(case)

    try:
        result = answer_student_question(case["question"])
    except Exception as exc:
        if expected.get("expect_error"):
            return _base_record(case, []) | {"error": str(exc)}
        failures.append(f"answer_student_question raised: {exc}")
        return _base_record(case, failures)

    if expected.get("expect_error"):
        failures.append("Expected error but answer_student_question succeeded")

    failures.extend(validate_mode(result.get("mode"), expected.get("mode")))
    failures.extend(check_text_rules(result.get("answer") or "", **{k: expected.get(k) for k in ("must_include", "must_not_include", "any_of") if expected.get(k)}))

    artifact = result.get("artifact") or {}
    failures.extend(validate_artifact_type(artifact, expected.get("artifact_type")))
    failures.extend(validate_sources_must_contain(result.get("sources"), expected.get("sources_must_contain")))

    graph_artifact = result.get("graph_artifact") or {}
    path_rows = graph_artifact.get("path_rows") or []
    failures.extend(
        validate_path_rows(
            path_rows,
            expected_paths_exact=expected.get("expected_paths_exact"),
            min_path_count=expected.get("min_path_count"),
        )
    )

    graph_context = result.get("graph_context")
    failures.extend(validate_graph_warning(graph_context, bool(expected.get("expect_graph_warning"))))

    sql_result = result.get("sql_result")
    failures.extend(
        validate_sql_result(
            sql_result,
            min_row_count=expected.get("min_row_count"),
            exact_row_count=expected.get("exact_row_count"),
        )
    )

    return _base_record(case, failures) | {
        "mode": result.get("mode"),
        "plan": result.get("plan"),
        "answer": result.get("answer"),
        "sources": result.get("sources"),
        "artifact": result.get("artifact"),
        "graph_artifact": result.get("graph_artifact"),
        "sql_result": result.get("sql_result"),
    }


def _collect_sources(graph_context: dict[str, Any] | None) -> list[str]:
    from student_rag.agents.deterministic import _graph_sources

    return _graph_sources(graph_context)


EVALUATORS = {
    "planning": evaluate_planning,
    "sql": evaluate_sql,
    "graph": evaluate_graph,
    "chart": evaluate_chart,
    "kg": evaluate_kg,
    "integration": evaluate_integration,
}
