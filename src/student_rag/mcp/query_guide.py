"""MCP guide tool: plan routing and fetch evidence without a full LLM pipeline."""

from __future__ import annotations

from typing import Any

from student_rag.agents.deterministic import get_graph_evidence, replan_if_needed
from student_rag.data.db import run_sql
from student_rag.query_routing import build_query_plan


def guide_student_query(question: str) -> dict[str, Any]:
    """Plan SQLite vs Neo4j routing and return evidence for the host model to synthesize."""
    plan = build_query_plan(question)

    sql_result: dict[str, Any] | None = None
    if plan["needs_sql"] and plan["sql"]:
        try:
            sql_result = run_sql(plan["sql"])
        except Exception as exc:
            sql_result = {
                "sql": plan["sql"],
                "error": str(exc),
                "rows": [],
                "columns": [],
                "row_count": 0,
            }

    graph_context = None
    if plan["needs_graph"]:
        graph_context = get_graph_evidence(
            question,
            plan.get("graph_query") or question,
        )

    plan, sql_result = replan_if_needed(question, plan, sql_result, graph_context)

    next_steps: list[str] = []
    if plan["needs_graph"] and graph_context:
        if not graph_context.get("students") and not graph_context.get("topic_matches"):
            if not graph_context.get("search_matches"):
                next_steps.append(
                    "Graph search returned no rows. If you need risk_level lists, use the "
                    "sql_result from this response (SQLite student_risk_summary)."
                )
    if sql_result and sql_result.get("row_count", 0) == 0 and plan.get("sql"):
        next_steps.append("SQL returned no rows. Call get_sqlite_schema and adjust the query.")

    return {
        "question": question,
        "guide": plan,
        "sql_result": sql_result,
        "graph_context": graph_context,
        "next_steps": next_steps,
        "instruction": (
            "Use sql_result for structured metrics and risk_level. Use graph_context for "
            "policy -> intervention paths. Do not call search_graph_context for risk-level lists."
        ),
    }
