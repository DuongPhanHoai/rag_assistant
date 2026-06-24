import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from student_rag.artifacts import generate_table_or_chart_spec
from student_rag.db import get_schema_summary as get_db_schema_summary
from student_rag.db import run_sql as run_student_sql
from student_rag.retrieval import retrieve_notes as retrieve_student_notes


mcp = FastMCP("student-management-rag")


@mcp.tool()
def get_schema_summary() -> str:
    """Return SQLite tables, views, and columns for the Student Management database."""
    return get_db_schema_summary()


@mcp.tool()
def run_sql(sql: str) -> str:
    """Run one read-only SELECT or WITH query against the Student Management SQLite database."""
    return json.dumps(run_student_sql(sql), ensure_ascii=False, default=str)


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
    return json.dumps(run_student_sql(sql), ensure_ascii=False, default=str)


@mcp.tool()
def analyze_at_risk_students() -> str:
    """Return at-risk students plus advising and policy context for explaining why and next actions."""
    sql = """
    SELECT student_name, program, advisor, avg_score, attendance_pct, balance_due, risk_level, risk_reasons
    FROM student_risk_summary
    WHERE risk_level IN ('high', 'medium')
    ORDER BY
        CASE risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
        avg_score ASC
    """
    sql_result = run_student_sql(sql)
    notes = retrieve_student_notes(
        "academic risk intervention low attendance low grades fee balance advising notes policy",
        k=5,
    )
    return json.dumps(
        {
            "structured_result": sql_result,
            "retrieved_context": notes,
            "guidance": (
                "Use structured_result for risk levels and metrics. Use retrieved_context for advising notes, "
                "policy thresholds, and recommended interventions."
            ),
        },
        ensure_ascii=False,
        default=str,
    )


@mcp.tool()
def get_scholarship_candidates() -> str:
    """Return raw structured scholarship candidate rows only.

    Prefer analyze_scholarship_candidates when the user asks why students qualify, asks for
    eligibility criteria, or mentions GPA/score, attendance, and fee status together.
    """
    sql = """
    SELECT student_name, program, avg_score, attendance_pct, balance_due, fee_status
    FROM student_risk_summary
    WHERE scholarship_candidate = 1
    ORDER BY avg_score DESC
    """
    result = run_student_sql(sql)
    result["guidance"] = (
        "avg_score is a weighted average score, not a GPA column. "
        "For policy criteria or explanation, call analyze_scholarship_candidates."
    )
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def analyze_scholarship_candidates() -> str:
    """Preferred tool for scholarship eligibility questions.

    Use this when the user asks who qualifies based on GPA/score, attendance, and fee status,
    or asks for policy context, reasons, criteria, or explanation.
    """
    sql = """
    SELECT student_name, program, avg_score, attendance_pct, balance_due, fee_status
    FROM student_risk_summary
    WHERE scholarship_candidate = 1
    ORDER BY avg_score DESC
    """
    sql_result = run_student_sql(sql)
    notes = retrieve_student_notes(
        "scholarship support policy GPA weighted average score attendance fee status financial need",
        k=4,
    )
    return json.dumps(
        {
            "structured_result": sql_result,
            "retrieved_context": notes,
            "guidance": (
                "Use structured_result for eligible students and metrics. Use retrieved_context for scholarship "
                "policy thresholds. Say weighted average score instead of GPA unless the user specifically asks for GPA."
            ),
        },
        ensure_ascii=False,
        default=str,
    )


@mcp.tool()
def retrieve_notes(query: str, k: int = 4) -> str:
    """Search advising notes, policies, and course descriptions with vector retrieval."""
    return json.dumps(retrieve_student_notes(query, k=k), ensure_ascii=False, default=str)


@mcp.tool()
def generate_artifact(question: str, sql_result_json: str, needs_chart: bool = False) -> str:
    """Create a Markdown table or Vega-Lite chart spec from a SQL result JSON string."""
    sql_result: dict[str, Any] = json.loads(sql_result_json)
    artifact = generate_table_or_chart_spec(
        question=question,
        sql_result=sql_result,
        needs_chart=needs_chart,
    )
    return json.dumps(artifact, ensure_ascii=False, default=str)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
