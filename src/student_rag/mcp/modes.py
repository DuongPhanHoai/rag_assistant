"""Register MCP tools for proxy vs tools mode."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Any, Iterator

from mcp.server.fastmcp import FastMCP

from student_rag.artifacts import generate_table_or_chart_spec
from student_rag.data.db import get_schema_summary as get_db_schema_summary
from student_rag.data.db import run_sql as run_student_sql
from student_rag.kg.neo4j_store import (
    Neo4jUnavailableError,
    get_graph_schema_summary,
    get_policy_intervention_path as neo4j_get_policy_intervention_path,
    get_related_risk_factors as neo4j_get_related_risk_factors,
    get_student_graph_context as neo4j_get_student_graph_context,
    is_neo4j_configured,
    query_knowledge_graph as neo4j_query_knowledge_graph,
    search_graph_context as neo4j_search_graph_context,
)
from student_rag.mcp.query_guide import guide_student_query as _run_query_guide
from student_rag.paths import DB_PATH, LLM_ONLINE_MODE, MCP_PROXY_LLM_TIMEOUT_SECONDS, STUDENT_MCP_MODE


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


@contextmanager
def _proxy_llm_timeout() -> Iterator[None]:
    """Use a longer LLM timeout while running the full agent pipeline in proxy mode."""
    import student_rag.llm as llm_module

    previous_get_llm = llm_module.get_llm
    llm_module.get_llm = lambda timeout=None: previous_get_llm(MCP_PROXY_LLM_TIMEOUT_SECONDS)
    try:
        yield
    finally:
        llm_module.get_llm = previous_get_llm


def _check_lm_studio_reachable() -> dict[str, Any]:
    import os

    import httpx

    base = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1").rstrip("/")
    url = f"{base}/models"
    try:
        response = httpx.get(url, timeout=5.0)
        return {"ok": response.status_code < 400, "url": url, "status_code": response.status_code}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def _agent_readiness() -> dict[str, Any]:
    sqlite_ok = DB_PATH.exists()
    neo4j_ok = False
    neo4j_error: str | None = None
    if is_neo4j_configured():
        try:
            neo4j_search_graph_context("Attendance", limit=1)
            neo4j_ok = True
        except Exception as exc:
            neo4j_error = str(exc)
    lm = _check_lm_studio_reachable() if LLM_ONLINE_MODE else {"ok": True, "skipped": True}
    return {
        "sqlite_ok": sqlite_ok,
        "sqlite_path": str(DB_PATH),
        "neo4j_ok": neo4j_ok,
        "neo4j_error": neo4j_error,
        "llm_online_mode": LLM_ONLINE_MODE,
        "lm_studio": lm,
        "proxy_llm_timeout_seconds": MCP_PROXY_LLM_TIMEOUT_SECONDS,
        "ready_for_proxy": sqlite_ok and (neo4j_ok or not is_neo4j_configured()) and (lm.get("ok") or not LLM_ONLINE_MODE),
    }


def register_mcp_tools(mcp: FastMCP, mode: str | None = None) -> str:
    """Register tools for the given mode. Returns the active mode name."""
    active = (mode or STUDENT_MCP_MODE).strip().lower()
    if active == "proxy":
        _register_proxy_tools(mcp)
    else:
        _register_tools_mode(mcp)
    return active


def _register_shared_info(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_mcp_mode() -> str:
        """Return the active MCP mode and what tools are exposed."""
        if STUDENT_MCP_MODE == "proxy":
            return _json(
                {
                    "mode": "proxy",
                    "description": (
                        "Questions are forwarded to the Student Management agent "
                        "(same pipeline as the CLI). Use ask_student_agent(question)."
                    ),
                    "tools": ["ask_student_agent", "check_agent_ready", "get_mcp_mode"],
                    "latency_note": (
                        "ask_student_agent runs plan + answer (two LLM calls). "
                        "Typical 30-180s. Thinking models may exceed MCP client timeout (~60-120s). "
                        "If tools time out, use mode=tools or a faster model."
                    ),
                }
            )
        return _json(
            {
                "mode": "tools",
                "description": (
                    "SQLite and Neo4j schemas plus low-level read-only tools. "
                    "The host model plans SQL/Cypher and synthesizes the answer."
                ),
                "tools": [
                    "get_mcp_mode",
                    "guide_student_query",
                    "get_sqlite_schema",
                    "get_neo4j_schema",
                    "run_sql",
                    "search_graph_context",
                    "query_knowledge_graph",
                    "get_student_graph_context",
                    "get_policy_intervention_path",
                    "get_related_risk_factors",
                    "generate_artifact",
                ],
                "recommended_first_tool": "guide_student_query",
            }
        )


def _register_proxy_tools(mcp: FastMCP) -> None:
    _register_shared_info(mcp)

    @mcp.tool()
    def check_agent_ready() -> str:
        """Quick health check (<5s): SQLite, Neo4j, LM Studio. Call before ask_student_agent."""
        return _json(_agent_readiness())

    @mcp.tool()
    def ask_student_agent(question: str) -> str:
        """Forward a question to the Student Management agent (CLI pipeline).

        Runs plan_question + answer_from_evidence (two LLM calls when online).
        Typical latency 30-180 seconds. If the MCP host times out, switch to tools mode
        (STUDENT_MCP_MODE=tools) or use a faster non-thinking model.
        """
        from student_rag.agents.deterministic import answer_student_question

        started = time.perf_counter()
        try:
            with _proxy_llm_timeout():
                result = answer_student_question(question)
        except Exception as exc:
            elapsed = round(time.perf_counter() - started, 2)
            message = str(exc)
            hint = None
            lowered = message.lower()
            if "timeout" in lowered or "timed out" in lowered:
                hint = (
                    "LM Studio or MCP client timed out. Set MCP_PROXY_LLM_TIMEOUT_SECONDS=180 in .env, "
                    "use a faster model, or switch to STUDENT_MCP_MODE=tools."
                )
            return _json(
                {
                    "question": question,
                    "error": message,
                    "duration_seconds": elapsed,
                    "hint": hint,
                    "readiness": _agent_readiness(),
                }
            )

        elapsed = round(time.perf_counter() - started, 2)
        return _json(
            {
                "question": question,
                "duration_seconds": elapsed,
                "mode": result.get("mode"),
                "answer": result.get("answer"),
                "plan": result.get("plan"),
                "steps": result.get("steps"),
                "sources": result.get("sources"),
                "sql_result": result.get("sql_result"),
                "graph_context": result.get("graph_context"),
                "artifact": result.get("artifact"),
                "graph_artifact": result.get("graph_artifact"),
            }
        )


def _register_tools_mode(mcp: FastMCP) -> None:
    _register_shared_info(mcp)

    @mcp.tool()
    def guide_student_query(question: str) -> str:
        """Call FIRST for student-management questions. Routes SQLite vs Neo4j and returns evidence.

        Use this instead of guessing run_sql vs search_graph_context. Risk levels (high/medium/low)
        come from SQLite student_risk_summary; Neo4j holds policy and intervention paths.
        """
        return _json(_run_query_guide(question))

    @mcp.tool()
    def get_sqlite_schema() -> str:
        """Return SQLite tables, views, and columns for the Student Management database."""
        return get_db_schema_summary()

    @mcp.tool()
    def get_schema_summary() -> str:
        """Alias for get_sqlite_schema (backward compatible with older MCP clients)."""
        return get_db_schema_summary()

    @mcp.tool()
    def get_neo4j_schema() -> str:
        """Return Neo4j node labels, relationship types, and common graph path patterns."""
        try:
            return get_graph_schema_summary()
        except Neo4jUnavailableError as exc:
            return get_graph_schema_summary() + f"\n\n(error: {exc})"

    @mcp.tool()
    def run_sql(sql: str) -> str:
        """Run one read-only SELECT or WITH query against the Student Management SQLite database."""
        return _json(run_student_sql(sql))

    @mcp.tool()
    def search_graph_context(query: str) -> str:
        """Search Neo4j for policy, risk-factor, and intervention context by keyword or topic.

        Not for risk_level lists (high/medium/low) — use guide_student_query or run_sql on
        student_risk_summary for those.
        """
        try:
            return _json(neo4j_search_graph_context(query))
        except Neo4jUnavailableError as exc:
            return _json({"error": str(exc), "query": query})

    @mcp.tool()
    def query_knowledge_graph(cypher: str) -> str:
        """Run one read-only Cypher query against the Neo4j knowledge graph."""
        try:
            return _json(neo4j_query_knowledge_graph(cypher))
        except (Neo4jUnavailableError, ValueError) as exc:
            return _json({"error": str(exc), "cypher": cypher})

    @mcp.tool()
    def get_student_graph_context(student_name: str) -> str:
        """Return Neo4j graph context for one student."""
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
    def generate_artifact(question: str, sql_result_json: str, needs_chart: bool = False) -> str:
        """Create a Markdown table or Vega-Lite chart spec from a SQL result JSON string."""
        sql_result: dict[str, Any] = json.loads(sql_result_json)
        artifact = generate_table_or_chart_spec(
            question=question,
            sql_result=sql_result,
            needs_chart=needs_chart,
        )
        return _json(artifact)
