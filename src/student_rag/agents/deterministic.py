import json
import logging
import re
from typing import Any

from student_rag.artifacts import generate_table_or_chart_spec, markdown_table
from student_rag.data.db import get_schema_summary, run_sql
from student_rag.kg.neo4j_store import (
    Neo4jUnavailableError,
    get_policy_intervention_path,
    get_related_risk_factors,
    search_graph_context,
)
from student_rag.logging_config import configure_logging
from student_rag.llm import get_llm
from student_rag.paths import LLM_ONLINE_MODE


logger = logging.getLogger(__name__)


STUDENT_NAMES = [
    "Maya Tran",
    "Noah Patel",
    "Lina Garcia",
    "Owen Smith",
    "Aisha Khan",
    "Minh Nguyen",
    "Emma Brown",
    "Carlos Reyes",
]


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response")
    return json.loads(match.group(0))


def _extract_student_names(question: str) -> list[str]:
    q = question.lower()
    return [name for name in STUDENT_NAMES if name.lower() in q]


def _heuristic_sql(question: str) -> str:
    q = question.lower()
    student_names = _extract_student_names(question)

    if student_names:
        student_name = student_names[0].replace("'", "''")
        return f"""
        SELECT student_name, program, advisor, avg_score, attendance_pct, balance_due,
               risk_level, risk_reasons, scholarship_candidate
        FROM student_risk_summary
        WHERE student_name = '{student_name}'
        """

    if "attendance" in q and ("trend" in q or "chart" in q or "month" in q):
        return """
        SELECT t.student_name, t.month, t.attendance_pct
        FROM attendance_trend t
        JOIN student_risk_summary r ON r.student_id = t.student_id AND r.term = t.term
        WHERE r.risk_level = 'high'
        ORDER BY t.student_name, t.month
        """

    if "scholarship" in q:
        return """
        SELECT student_name, program, avg_score, attendance_pct, balance_due, scholarship_candidate
        FROM student_risk_summary
        WHERE scholarship_candidate = 1
        ORDER BY avg_score DESC
        """

    if "course" in q or "average" in q or "weak" in q or "grade" in q:
        return """
        SELECT course_id, course_name, enrolled_students, avg_score, avg_attendance_pct
        FROM course_performance_summary
        ORDER BY avg_score ASC
        """

    if "fee" in q or "balance" in q or "financial" in q:
        return """
        SELECT student_name, term, total_due, amount_paid, balance_due, status
        FROM fee_summary
        ORDER BY balance_due DESC
        """

    if "at risk" in q or "risk" in q:
        return """
        SELECT student_name, program, advisor, avg_score, attendance_pct, balance_due,
               risk_level, risk_reasons, scholarship_candidate
        FROM student_risk_summary
        WHERE risk_level IN ('high', 'medium')
        ORDER BY
            CASE risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            avg_score ASC
        """

    return """
    SELECT student_name, program, advisor, avg_score, attendance_pct, balance_due,
           risk_level, risk_reasons, scholarship_candidate
    FROM student_risk_summary
    ORDER BY
        CASE risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
        avg_score ASC
    """


def _needs_graph_heuristic(question: str) -> bool:
    q = question.lower()
    return any(
        word in q
        for word in [
            "policy",
            "policies",
            "intervention",
            "advising",
            "why",
            "explain",
            "risk factor",
            "risk factors",
            "recommend",
            "support",
            "scholarship",
            "irregular attendance",
        ]
    )


def _fallback_plan(question: str) -> dict[str, Any]:
    q = question.lower()
    needs_chart = any(word in q for word in ["chart", "trend", "plot", "graph"])
    student_names = _extract_student_names(question)
    needs_sql = bool(student_names) or not _needs_graph_heuristic(question) or needs_chart
    return {
        "question": question,
        "reasoning": "Heuristic plan (LLM_ONLINE_MODE=false).",
        "needs_sql": needs_sql,
        "needs_graph": _needs_graph_heuristic(question),
        "needs_chart": needs_chart,
        "graph_query": question,
        "student_names": student_names,
        "sql": _heuristic_sql(question),
        "used_llm_plan": False,
    }


def plan_question(question: str) -> dict[str, Any]:
    if not LLM_ONLINE_MODE:
        return _fallback_plan(question)

    schema = get_schema_summary()
    prompt = f"""
You are planning a small agentic RAG workflow over a Student Management SQLite database and a Neo4j
knowledge graph built from policy and advising CSV files with AutoSchemaKG.

Return only JSON with these keys:
- reasoning: short explanation
- needs_sql: boolean
- needs_graph: boolean
- needs_chart: boolean
- graph_query: short text to search graph context for policies, interventions, and risk factors
- sql: a single read-only SELECT or WITH query, or an empty string

Prefer the views student_risk_summary, course_performance_summary, attendance_trend, assessment_scores,
attendance_summary, and fee_summary when they answer the question.

Schema:
{schema}

Question:
{question}
"""
    logger.info("plan_question prompt:\n%s", prompt.strip())
    try:
        response = get_llm().invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        logger.info("plan_question LLM response:\n%s", content)
        plan = _extract_json(content)
        used_llm_plan = True
    except Exception as exc:
        raise RuntimeError(f"LM Studio connection failed during planning: {exc}") from exc

    fallback = _fallback_plan(question)
    fallback["used_llm_plan"] = used_llm_plan
    merged_plan = {
        "question": question,
        "reasoning": str(plan.get("reasoning") or fallback["reasoning"]),
        "needs_sql": bool(plan.get("needs_sql", fallback["needs_sql"])),
        "needs_graph": bool(plan.get("needs_graph", fallback["needs_graph"])),
        "needs_chart": bool(plan.get("needs_chart", fallback["needs_chart"])),
        "graph_query": str(plan.get("graph_query") or fallback["graph_query"]),
        "student_names": _extract_student_names(question),
        "sql": str(plan.get("sql") or fallback["sql"]),
        "used_llm_plan": used_llm_plan,
    }
    logger.info("plan_question plan:\n%s", json.dumps(merged_plan, ensure_ascii=False, indent=2))
    return merged_plan


def decompose_query_request(plan: dict[str, Any]) -> list[dict[str, str]]:
    steps = [{"step": "plan", "detail": plan.get("reasoning", "")}]
    if plan.get("needs_sql"):
        steps.append({"step": "query_structured_data", "detail": plan.get("sql", "")})
    if plan.get("needs_graph"):
        steps.append(
            {
                "step": "query_knowledge_graph",
                "detail": plan.get("graph_query", ""),
            }
        )
    if plan.get("needs_chart"):
        steps.append({"step": "generate_chart", "detail": "Create a Vega-Lite chart spec from SQL rows."})
    else:
        steps.append({"step": "generate_table", "detail": "Create a compact Markdown table from SQL rows."})
    steps.append({"step": "replan", "detail": "Check whether evidence is missing and run a fallback query if needed."})
    steps.append({"step": "answer", "detail": "Synthesize SQL evidence, graph context, and sources."})
    return steps


def _graph_topic_terms(question: str) -> list[str]:
    q = question.lower()
    terms: list[str] = []
    if "irregular attendance" in q:
        terms.append("Irregular Attendance")
    if "financial hold" in q or "balance due" in q:
        terms.append("Balance Due Greater Than 500")
    if "scholarship" in q:
        terms.append("Scholarship Support Policy")
    return terms


def get_graph_evidence(question: str, graph_query: str) -> dict[str, Any]:
    student_names = _extract_student_names(question) or _extract_student_names(graph_query)
    evidence: dict[str, Any] = {
        "students": [],
        "topic_matches": [],
        "search_matches": [],
    }

    try:
        for student_name in student_names:
            evidence["students"].append(
                {
                    "student_name": student_name,
                    "risk_factors": get_related_risk_factors(student_name),
                    "policy_paths": get_policy_intervention_path(student_name),
                }
            )

        for term in _graph_topic_terms(question):
            evidence["topic_matches"].append(search_graph_context(term))

        if not evidence["students"] and not evidence["topic_matches"]:
            evidence["search_matches"] = search_graph_context(graph_query).get("matches", [])
    except Neo4jUnavailableError as exc:
        evidence["warning"] = str(exc)

    return evidence


def replan_if_needed(
    question: str,
    plan: dict[str, Any],
    sql_result: dict[str, Any] | None,
    graph_context: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if sql_result and sql_result.get("row_count", 0) > 0:
        return plan, sql_result

    fallback = _fallback_plan(question)
    fallback["reasoning"] = "Replanned because the first SQL query returned no rows."
    if fallback.get("sql") == plan.get("sql"):
        return plan, sql_result

    try:
        return fallback, run_sql(fallback["sql"])
    except Exception:
        return plan, sql_result


def _graph_sources(graph_context: dict[str, Any] | None) -> list[str]:
    if not graph_context:
        return []

    sources: set[str] = set()
    for student_block in graph_context.get("students", []):
        for row in student_block.get("risk_factors", {}).get("risk_factors", []):
            if row.get("source_doc"):
                sources.add(row["source_doc"])
        for row in student_block.get("policy_paths", {}).get("paths", []):
            if row.get("source_doc"):
                sources.add(row["source_doc"])

    for match_group in graph_context.get("topic_matches", []):
        for row in match_group.get("matches", []):
            if row.get("source_doc"):
                sources.add(row["source_doc"])

    for row in graph_context.get("search_matches", []):
        if row.get("source_doc"):
            sources.add(row["source_doc"])

    return sorted(sources)


def _format_graph_evidence(graph_context: dict[str, Any] | None) -> list[str]:
    if not graph_context:
        return []

    lines: list[str] = []
    if graph_context.get("warning"):
        lines.append(graph_context["warning"])
        lines.append("")

    for student_block in graph_context.get("students", []):
        student_name = student_block["student_name"]
        lines.append(f"Graph evidence for {student_name}:")
        risk_rows = student_block.get("risk_factors", {}).get("risk_factors", [])
        if risk_rows:
            lines.append("Risk factors:")
            for row in risk_rows:
                lines.append(f"- {row.get('risk_factor')}")
        else:
            lines.append("Risk factors: none found in Neo4j.")

        path_rows = student_block.get("policy_paths", {}).get("paths", [])
        if path_rows:
            lines.append("Policy and intervention paths:")
            for row in path_rows:
                lines.append(
                    f"- {row.get('risk_factor')} -> {row.get('policy')} -> {row.get('intervention')}"
                )
        else:
            lines.append("Policy and intervention paths: none found in Neo4j.")
        lines.append("")

    for match_group in graph_context.get("topic_matches", []):
        query = match_group.get("query", "topic")
        lines.append(f"Graph topic matches for '{query}':")
        for row in match_group.get("matches", [])[:5]:
            related = row.get("related_name")
            relation = row.get("relation")
            name = row.get("name")
            if related and relation:
                lines.append(f"- {name} -[{relation}]-> {related}")
            elif name:
                lines.append(f"- {name}")
        lines.append("")

    for row in graph_context.get("search_matches", [])[:5]:
        related = row.get("related_name")
        relation = row.get("relation")
        name = row.get("name")
        if related and relation:
            lines.append(f"- {name} -[{relation}]-> {related}")
        elif name:
            lines.append(f"- {name}")

    return lines


def _fallback_answer(
    question: str,
    sql_result: dict[str, Any] | None,
    graph_context: dict[str, Any] | None,
    artifact: dict[str, Any],
) -> str:
    if not LLM_ONLINE_MODE:
        intro = "LLM online mode is disabled (LLM_ONLINE_MODE=false). This answer is synthesized from SQLite and Neo4j evidence only."
    else:
        intro = "LM Studio is unavailable. This answer is synthesized directly from SQLite and Neo4j evidence."

    lines = [intro, ""]

    graph_lines = _format_graph_evidence(graph_context)
    if graph_lines:
        lines.extend(graph_lines)

    if sql_result and sql_result.get("rows"):
        lines.append("Structured evidence:")
        lines.append(markdown_table(sql_result["rows"], sql_result["columns"]))
        lines.append("")

    if not graph_lines and not (sql_result and sql_result.get("rows")):
        lines.append("No usable SQLite or Neo4j evidence was found for this question.")

    if artifact["type"] == "chart":
        lines.append("A Vega-Lite chart spec is included in the result under `artifact.chart_spec`.")
    return "\n".join(lines).strip()


def answer_from_evidence(
    question: str,
    plan: dict[str, Any],
    sql_result: dict[str, Any] | None,
    graph_context: dict[str, Any] | None,
    artifact: dict[str, Any],
) -> tuple[str, bool]:
    if not LLM_ONLINE_MODE:
        return _fallback_answer(question, sql_result, graph_context, artifact), False

    evidence = {
        "plan": plan,
        "sql_result": sql_result,
        "graph_context": graph_context,
        "artifact": artifact,
    }
    prompt = f"""
Answer the student management question using only the evidence below.

Rules:
- Be concise and factual.
- Mention when the answer depends on both structured data and graph policy or intervention context.
- If a chart spec is included, describe what the chart shows.
- Include practical next actions when the question is about risk or intervention.

Question:
{question}

Evidence JSON:
{json.dumps(evidence, ensure_ascii=False, indent=2)}
"""
    logger.info("answer_from_evidence prompt:\n%s", prompt.strip())
    try:
        response = get_llm().invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return content, True
    except Exception as exc:
        raise RuntimeError(f"LM Studio connection failed during answer synthesis: {exc}") from exc


def answer_student_question(question: str) -> dict[str, Any]:
    plan = plan_question(question)
    steps = decompose_query_request(plan)

    sql_result = run_sql(plan["sql"]) if plan.get("needs_sql") else None
    graph_context = (
        get_graph_evidence(question, plan.get("graph_query") or question)
        if plan.get("needs_graph")
        else None
    )
    plan, sql_result = replan_if_needed(question, plan, sql_result, graph_context)

    artifact = generate_table_or_chart_spec(
        question=question,
        sql_result=sql_result or {"rows": [], "columns": []},
        needs_chart=bool(plan.get("needs_chart")),
    )
    answer, used_llm_answer = answer_from_evidence(question, plan, sql_result, graph_context, artifact)
    sources = _graph_sources(graph_context)

    return {
        "question": question,
        "plan": plan,
        "steps": steps,
        "sql_result": sql_result,
        "graph_context": graph_context,
        "artifact": artifact,
        "answer": answer,
        "sources": sources,
        "mode": "llm" if used_llm_answer else "offline_evidence",
    }


def main() -> None:
    configure_logging()
    print("Student Agentic RAG sample. Type 'quit' to exit.")
    while True:
        user_question = input("\nAsk a student management question: ").strip()
        if user_question.lower() in {"quit", "exit"}:
            break
        try:
            result = answer_student_question(user_question)
            print(f"\nMode: {result.get('mode', 'unknown')}")
            print("\nPlan:")
            print(json.dumps(result["plan"], indent=2))
            print("\nAnswer:\n", result["answer"])
            if result["artifact"]["type"] == "table":
                print("\nTable:\n", result["artifact"]["markdown"])
            else:
                print("\nChart spec:\n", json.dumps(result["artifact"]["chart_spec"], indent=2))
            print("\nSources:")
            for source in result["sources"]:
                print(" -", source)
        except Exception as exc:
            print("Error:", exc)


if __name__ == "__main__":
    main()
