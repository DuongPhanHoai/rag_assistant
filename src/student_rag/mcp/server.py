import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from student_rag.artifacts import generate_table_or_chart_spec
from student_rag.data.db import get_schema_summary as get_db_schema_summary
from student_rag.data.db import run_sql as run_student_sql
from student_rag.kg.neo4j_store import (
    Neo4jUnavailableError,
    get_policy_intervention_path as neo4j_get_policy_intervention_path,
    get_related_risk_factors as neo4j_get_related_risk_factors,
    get_student_graph_context as neo4j_get_student_graph_context,
    query_knowledge_graph as neo4j_query_knowledge_graph,
)
from student_rag.logging_config import configure_logging


mcp = FastMCP("student-management-rag")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Simple HTTP health check for remote connectivity testing."""
    return JSONResponse({"status": "ok", "service": "student-management-rag"})


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _graph_bundle_for_students(student_names: list[str]) -> dict[str, Any]:
    if not student_names:
        return {"students": [], "warning": "No student names available for graph lookup."}

    students: list[dict[str, Any]] = []
    warning: str | None = None
    for student_name in student_names[:5]:
        try:
            students.append(
                {
                    "student_name": student_name,
                    "graph_context": neo4j_get_student_graph_context(student_name),
                    "policy_intervention_paths": neo4j_get_policy_intervention_path(student_name),
                    "risk_factors": neo4j_get_related_risk_factors(student_name),
                }
            )
        except Neo4jUnavailableError as exc:
            warning = str(exc)
            break
    return {"students": students, "warning": warning}


def _student_names_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for row in rows:
        name = row.get("student_name")
        if isinstance(name, str) and name not in names:
            names.append(name)
    return names


@mcp.tool()
def get_schema_summary() -> str:
    """Return SQLite tables, views, and columns for the Student Management database."""
    return get_db_schema_summary()


@mcp.tool()
def run_sql(sql: str) -> str:
    """Run one read-only SELECT or WITH query against the Student Management SQLite database."""
    return _json(run_student_sql(sql))


@mcp.tool()
def get_student_graph_context(student_name: str) -> str:
    """Return Neo4j graph context for one student from the AutoSchemaKG-built knowledge graph."""
    try:
        return _json(neo4j_get_student_graph_context(student_name))
    except Neo4jUnavailableError as exc:
        return _json({"error": str(exc), "student_name": student_name})


@mcp.tool()
def get_policy_intervention_path(student_name: str) -> str:
    """Return policy and intervention paths for a student based on risk factors in Neo4j."""
    try:
        return _json(neo4j_get_policy_intervention_path(student_name))
    except Neo4jUnavailableError as exc:
        return _json({"error": str(exc), "student_name": student_name})


@mcp.tool()
def get_related_risk_factors(student_name: str) -> str:
    """Return risk factors linked to a student in the Neo4j knowledge graph."""
    try:
        return _json(neo4j_get_related_risk_factors(student_name))
    except Neo4jUnavailableError as exc:
        return _json({"error": str(exc), "student_name": student_name})


@mcp.tool()
def query_knowledge_graph(cypher: str) -> str:
    """Run one read-only Cypher query against the Neo4j knowledge graph."""
    try:
        return _json(neo4j_query_knowledge_graph(cypher))
    except (Neo4jUnavailableError, ValueError) as exc:
        return _json({"error": str(exc), "cypher": cypher})


@mcp.tool()
def ask_student_management(question: str) -> str:
    """Default tool for plain-language Student Management questions.

    Routes common questions to structured SQLite queries and, when available, Neo4j graph context.
    """
    q = question.lower()

    if "scholarship" in q:
        return analyze_scholarship_candidates()

    if "risk" in q or "at risk" in q or "intervention" in q:
        return analyze_at_risk_students()

    if "attendance" in q and ("trend" in q or "chart" in q or "month" in q or "graph" in q):
        sql_result = run_student_sql(
            """
            SELECT t.student_name, t.month, t.attendance_pct
            FROM attendance_trend t
            JOIN student_risk_summary r ON r.student_id = t.student_id AND r.term = t.term
            WHERE r.risk_level = 'high'
            ORDER BY t.student_name, t.month
            """
        )
        artifact = generate_table_or_chart_spec(question, sql_result, needs_chart=True)
        return _json(
            {
                "structured_result": sql_result,
                "artifact": artifact,
                "recommended_response_style": "Describe the attendance trend using the structured metrics.",
            }
        )

    if "course" in q or "grade" in q or "average" in q or "weak" in q:
        sql_result = run_student_sql(
            """
            SELECT course_id, course_name, enrolled_students, avg_score, avg_attendance_pct
            FROM course_performance_summary
            ORDER BY avg_score ASC
            """
        )
        return _json(
            {
                "structured_result": sql_result,
                "recommended_response_style": "Summarize course performance by average score and attendance.",
            }
        )

    if "fee" in q or "balance" in q or "financial" in q:
        sql_result = run_student_sql(
            """
            SELECT student_name, term, total_due, amount_paid, balance_due, status
            FROM fee_summary
            ORDER BY balance_due DESC
            """
        )
        return _json(
            {
                "structured_result": sql_result,
                "recommended_response_style": "Explain fee balances from the structured rows.",
            }
        )

    return _json(
        {
            "schema": get_db_schema_summary(),
            "recommended_response_style": (
                "Use the schema to choose a read-only SQL query or Neo4j graph tool, "
                "then call run_sql, query_knowledge_graph, or a high-level data tool."
            ),
        }
    )


@mcp.tool()
def get_at_risk_students() -> str:
    """Return students whose risk_level is high or medium, with reasons and key risk metrics."""
    sql = """
    SELECT student_name, program, advisor, avg_score, attendance_pct, balance_due, risk_level, risk_reasons
    FROM student_risk_summary
    WHERE risk_level IN ('high', 'medium')
    ORDER BY
        CASE risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
        avg_score ASC
    """
    return _json(run_student_sql(sql))


@mcp.tool()
def analyze_at_risk_students() -> str:
    """Return at-risk students with structured metrics, graph context, and interpretation guidance."""
    sql_result = run_student_sql(
        """
        SELECT student_name, program, advisor, avg_score, attendance_pct, balance_due, risk_level, risk_reasons
        FROM student_risk_summary
        WHERE risk_level IN ('high', 'medium')
        ORDER BY
            CASE risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            avg_score ASC
        """
    )
    graph_bundle = _graph_bundle_for_students(_student_names_from_rows(sql_result.get("rows", [])))
    return _json(
        {
            "structured_result": sql_result,
            "graph_context": graph_bundle,
            "guidance": (
                "Use structured_result for risk levels and metrics. High-risk triggers: avg_score < 70, "
                "attendance_pct < 75, balance_due > 500. Medium-risk indicators: avg_score < 80, "
                "attendance_pct < 85, balance_due > 0. If risk_reasons is empty for a medium-risk student, "
                "infer the reason from these metrics and graph_context policy/intervention paths."
            ),
        },
    )


@mcp.tool()
def get_scholarship_candidates() -> str:
    """Return scholarship candidate rows from student_risk_summary where scholarship_candidate = 1."""
    sql = """
    SELECT student_name, program, avg_score, attendance_pct, balance_due, fee_status
    FROM student_risk_summary
    WHERE scholarship_candidate = 1
    ORDER BY avg_score DESC
    """
    result = run_student_sql(sql)
    result["guidance"] = "avg_score is a weighted average score, not a GPA column."
    return _json(result)


@mcp.tool()
def analyze_scholarship_candidates() -> str:
    """Return scholarship candidates with structured metrics, graph context, and interpretation guidance."""
    sql_result = run_student_sql(
        """
        SELECT student_name, program, avg_score, attendance_pct, balance_due, fee_status
        FROM student_risk_summary
        WHERE scholarship_candidate = 1
        ORDER BY avg_score DESC
        """
    )
    graph_bundle = _graph_bundle_for_students(_student_names_from_rows(sql_result.get("rows", [])))
    return _json(
        {
            "structured_result": sql_result,
            "graph_context": graph_bundle,
            "guidance": (
                "Use structured_result for eligible students and metrics. scholarship_candidate = 1 means yes. "
                "Use graph_context for scholarship policy evidence from Neo4j when explaining eligibility."
            ),
        },
    )


@mcp.tool()
def generate_artifact(question: str, sql_result_json: str, needs_chart: bool = False) -> str:
    """Create a Markdown table or Vega-Lite chart spec from a SQL result JSON string."""
    sql_result: dict[str, Any] = json.loads(sql_result_json)
    artifact = generate_table_or_chart_spec(
        question=question,
        sql_result=sql_result,
        needs_chart=needs_chart,
    )
    return _json(artifact)


def main() -> None:
    configure_logging()
    mcp.run()


if __name__ == "__main__":
    main()
