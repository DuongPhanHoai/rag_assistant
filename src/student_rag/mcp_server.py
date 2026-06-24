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
def get_scholarship_candidates() -> str:
    """Return students who qualify for scholarship support. Uses scholarship_candidate = 1."""
    sql = """
    SELECT student_name, program, avg_score, attendance_pct, balance_due, fee_status
    FROM student_risk_summary
    WHERE scholarship_candidate = 1
    ORDER BY avg_score DESC
    """
    return json.dumps(run_student_sql(sql), ensure_ascii=False, default=str)


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
