from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TEST_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TEST_DIR / "fixtures"
RESULTS_DIR = TEST_DIR / "results"

READ_ONLY_SQL_PATTERN = re.compile(
    r"^\s*(with\b|select\b)",
    re.IGNORECASE | re.DOTALL,
)
FORBIDDEN_SQL_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|pragma)\b",
    re.IGNORECASE,
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {path}")
    return data


def load_fixture(relative_path: str) -> Any:
    return load_json(FIXTURES_DIR / relative_path)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def new_run_id() -> str:
    return datetime.now(UTC).isoformat()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def check_text_rules(
    text: str,
    must_include: list[str] | None = None,
    must_not_include: list[str] | None = None,
    any_of: list[str] | None = None,
) -> list[str]:
    """Return human-readable failure messages for answer-text checks."""
    failures: list[str] = []
    normalized = normalize_text(text)

    for phrase in must_include or []:
        if normalize_text(phrase) not in normalized:
            failures.append(f'Missing required phrase: "{phrase}"')

    for phrase in must_not_include or []:
        if normalize_text(phrase) in normalized:
            failures.append(f'Forbidden phrase present: "{phrase}"')

    if any_of:
        if not any(normalize_text(phrase) in normalized for phrase in any_of):
            joined = '", "'.join(any_of)
            failures.append(f'Expected at least one of: "{joined}"')

    return failures


def validate_sql_safety(sql: str) -> list[str]:
    failures: list[str] = []
    cleaned = sql.strip()
    if not cleaned:
        failures.append("SQL is empty")
        return failures
    if not READ_ONLY_SQL_PATTERN.match(cleaned):
        failures.append("SQL must start with SELECT or WITH")
    if FORBIDDEN_SQL_PATTERN.search(cleaned):
        failures.append("SQL contains a forbidden mutating keyword")
    return failures


def validate_sql_fragments(sql: str, fragments: list[str] | None) -> list[str]:
    failures: list[str] = []
    lowered = sql.lower()
    for fragment in fragments or []:
        if fragment.lower() not in lowered:
            failures.append(f'SQL missing expected fragment: "{fragment}"')
    return failures


def validate_plan_invariants(plan: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    needs_sql = bool(plan.get("needs_sql"))
    needs_graph = bool(plan.get("needs_graph"))
    needs_chart = bool(plan.get("needs_chart"))
    sql = str(plan.get("sql") or "").strip()
    graph_query = str(plan.get("graph_query") or "").strip()

    if needs_chart and not needs_sql:
        failures.append("Invariant: needs_chart=true requires needs_sql=true")
    if not needs_sql and sql:
        failures.append("Invariant: needs_sql=false requires empty sql")
    if not needs_graph and graph_query:
        failures.append("Invariant: needs_graph=false requires empty graph_query")
    return failures


def validate_plan_flags(plan: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key in ("needs_sql", "needs_graph", "needs_chart"):
        if key not in expected:
            continue
        actual = bool(plan.get(key))
        wanted = bool(expected[key])
        if actual != wanted:
            failures.append(f"{key}: expected {wanted}, got {actual}")
    return failures


def summarize_case(case_id: str, failures: list[str]) -> dict[str, Any]:
    return {
        "id": case_id,
        "status": "pass" if not failures else "fail",
        "failure_count": len(failures),
        "failures": failures,
    }


def resolve_fixture_value(value: Any) -> Any:
    if isinstance(value, str) and value.endswith(".json"):
        return load_fixture(value)
    return value


def validate_artifact_type(artifact: dict[str, Any] | None, expected_type: str | None) -> list[str]:
    if not expected_type:
        return []
    actual = (artifact or {}).get("type")
    if actual != expected_type:
        return [f"artifact.type: expected {expected_type}, got {actual}"]
    return []


def validate_sources(actual_sources: list[str] | None, expected_sources: list[str] | None) -> list[str]:
    failures: list[str] = []
    actual = set(actual_sources or [])
    for source in expected_sources or []:
        if source not in actual:
            failures.append(f'Missing expected source: "{source}"')
    return failures


def discover_purpose_cases(purposes_dir: Path, purpose_filter: str | None = None) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for cases_path in sorted(purposes_dir.glob("*/cases.json")):
        purpose_name = cases_path.parent.name
        if purpose_filter and purpose_filter not in purpose_name:
            continue
        for case in load_cases(cases_path):
            case = dict(case)
            case.setdefault("purpose", purpose_name)
            case["_cases_path"] = str(cases_path)
            cases.append(case)
    return cases


def case_requires_llm(case: dict[str, Any]) -> bool:
    if "requires_llm" in case:
        return bool(case["requires_llm"])
    layer = str(case.get("layer") or "")
    case_id = str(case.get("id") or "")
    if layer in {"sql_only", "graph_only", "artifact_only"}:
        return False
    if layer == "infra" and case_id in {"offline_mode", "offline_mode_e2e"}:
        return False
    if layer in {"plan", "pipeline", "e2e", "replan", "answer", "fidelity"}:
        return True
    return False


def extract_path_rows(
    graph_context: dict[str, Any] | None,
    graph_artifact: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if graph_artifact and graph_artifact.get("path_rows") is not None:
        return list(graph_artifact["path_rows"])
    rows: list[dict[str, Any]] = []
    for student_block in (graph_context or {}).get("students", []):
        rows.extend(student_block.get("policy_paths", {}).get("paths", []))
    return rows


def extract_risk_rows(
    graph_context: dict[str, Any] | None,
    graph_artifact: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if graph_artifact and graph_artifact.get("risk_rows") is not None:
        return list(graph_artifact["risk_rows"])
    rows: list[dict[str, Any]] = []
    for student_block in (graph_context or {}).get("students", []):
        rows.extend(student_block.get("risk_factors", {}).get("risk_factors", []))
    return rows


def _path_row_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key, value in expected.items():
        actual_value = str(actual.get(key) or "").strip()
        expected_value = str(value).strip()
        if normalize_text(actual_value) != normalize_text(expected_value):
            return False
    return True


def validate_path_rows(
    path_rows: list[dict[str, Any]],
    expected_paths_exact: int | None = None,
    expected_path_rows: list[dict[str, Any]] | None = None,
    min_path_count: int | None = None,
) -> list[str]:
    failures: list[str] = []
    count = len(path_rows)

    if expected_paths_exact is not None and count != expected_paths_exact:
        failures.append(f"path_rows count: expected {expected_paths_exact}, got {count}")

    if min_path_count is not None and count < min_path_count:
        failures.append(f"path_rows count: expected at least {min_path_count}, got {count}")

    for index, expected in enumerate(expected_path_rows or []):
        if not any(_path_row_matches(row, expected) for row in path_rows):
            failures.append(f"Missing expected path row #{index + 1}: {expected}")

    return failures


def validate_sources_must_contain(actual_sources: list[str] | None, required: list[str] | None) -> list[str]:
    return validate_sources(actual_sources, required)


def validate_sources_any_of(actual_sources: list[str] | None, options: list[str] | None) -> list[str]:
    if not options:
        return []
    actual = set(actual_sources or [])
    if not any(option in actual for option in options):
        joined = '", "'.join(options)
        return [f'Expected at least one source from: "{joined}"']
    return []


def validate_sql_result(
    sql_result: dict[str, Any] | None,
    *,
    min_row_count: int | None = None,
    max_row_count: int | None = None,
    exact_row_count: int | None = None,
    columns_must_include: list[str] | None = None,
    row_must_include: dict[str, Any] | None = None,
    expect_error: bool = False,
) -> list[str]:
    failures: list[str] = []
    result = sql_result or {}

    if expect_error:
        if not result.get("error"):
            failures.append("Expected SQL error but query succeeded")
        return failures

    if result.get("error"):
        failures.append(f"SQL error: {result['error']}")
        return failures

    row_count = int(result.get("row_count", len(result.get("rows") or [])))
    if min_row_count is not None and row_count < min_row_count:
        failures.append(f"row_count: expected at least {min_row_count}, got {row_count}")
    if max_row_count is not None and row_count > max_row_count:
        failures.append(f"row_count: expected at most {max_row_count}, got {row_count}")
    if exact_row_count is not None and row_count != exact_row_count:
        failures.append(f"row_count: expected {exact_row_count}, got {row_count}")

    columns = set(result.get("columns") or [])
    for column in columns_must_include or []:
        if column not in columns:
            failures.append(f'Missing expected column: "{column}"')

    if row_must_include:
        rows = result.get("rows") or []
        if not any(all(row.get(k) == v for k, v in row_must_include.items()) for row in rows):
            failures.append(f"No row matched expected values: {row_must_include}")

    return failures


def validate_chart_spec(artifact: dict[str, Any] | None, expected: dict[str, Any] | None) -> list[str]:
    if not expected:
        return []
    failures: list[str] = []
    chart_spec = (artifact or {}).get("chart_spec") or {}

    for key in ("x_field", "y_field", "mark"):
        if key not in expected:
            continue
        if key == "mark":
            actual = chart_spec.get("mark")
        elif key == "x_field":
            actual = ((chart_spec.get("encoding") or {}).get("x") or {}).get("field")
        else:
            actual = ((chart_spec.get("encoding") or {}).get("y") or {}).get("field")
        wanted = expected[key]
        if actual != wanted:
            failures.append(f"chart_spec.{key}: expected {wanted!r}, got {actual!r}")

    if "min_data_points" in expected:
        values = ((chart_spec.get("data") or {}).get("values")) or []
        minimum = int(expected["min_data_points"])
        if len(values) < minimum:
            failures.append(f"chart data points: expected at least {minimum}, got {len(values)}")

    return failures


def validate_student_names_in_graph(
    graph_context: dict[str, Any] | None,
    must_include: list[str] | None = None,
) -> list[str]:
    if not must_include:
        return []
    found: set[str] = set()
    for student_block in (graph_context or {}).get("students", []):
        name = student_block.get("student_name")
        if name:
            found.add(normalize_text(name))
    for match_group in (graph_context or {}).get("topic_matches", []):
        for row in match_group.get("matches", []):
            if row.get("name"):
                found.add(normalize_text(row["name"]))
    failures: list[str] = []
    for name in must_include:
        if normalize_text(name) not in found:
            failures.append(f'Missing expected student/topic name in graph evidence: "{name}"')
    return failures


def validate_graph_warning(graph_context: dict[str, Any] | None, expect_warning: bool = False) -> list[str]:
    has_warning = bool((graph_context or {}).get("warning"))
    if expect_warning and not has_warning:
        return ["Expected graph_context.warning but none was set"]
    if not expect_warning and has_warning:
        return [f"Unexpected graph_context.warning: {graph_context.get('warning')}"]
    return []


def validate_mode(actual_mode: str | None, expected_mode: str | None) -> list[str]:
    if not expected_mode:
        return []
    if actual_mode != expected_mode:
        return [f"mode: expected {expected_mode!r}, got {actual_mode!r}"]
    return []


def merge_expected(case: dict[str, Any]) -> dict[str, Any]:
    return dict(case.get("expected") or {})
