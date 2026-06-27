"""Shared SQLite vs Neo4j routing heuristics for the CLI agent and MCP guide tool."""

from __future__ import annotations

from typing import Any

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


def extract_student_names(question: str) -> list[str]:
    q = question.lower()
    return [name for name in STUDENT_NAMES if name.lower() in q]


def heuristic_sql(question: str) -> str:
    q = question.lower()
    student_names = extract_student_names(question)

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


def needs_graph_heuristic(question: str) -> bool:
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


def graph_topic_terms(question: str) -> list[str]:
    q = question.lower()
    terms: list[str] = []
    if "irregular attendance" in q:
        terms.append("Irregular Attendance")
    if "financial hold" in q or "balance due" in q:
        terms.append("Balance Due Greater Than 500")
    if "scholarship" in q:
        terms.append("Scholarship Support Policy")
    return terms


def classify_intent(question: str) -> str:
    q = question.lower()
    if extract_student_names(question):
        if needs_graph_heuristic(question):
            return "student_detail_with_policy"
        return "student_detail"
    if any(word in q for word in ["chart", "trend", "plot"]):
        return "chart_or_trend"
    if any(word in q for word in ["policy", "policies", "intervention"]) and "risk" not in q:
        return "policy_only"
    if "scholarship" in q:
        return "scholarship"
    if "course" in q or "grade" in q:
        return "course_performance"
    if "fee" in q or "balance" in q:
        return "fees"
    if "risk" in q or "at risk" in q:
        return "at_risk_list"
    return "general_summary"


def build_query_plan(question: str) -> dict[str, Any]:
    """Return routing guidance for SQLite vs Neo4j without calling either store."""
    q = question.lower()
    student_names = extract_student_names(question)
    needs_graph = needs_graph_heuristic(question)
    needs_chart = any(word in q for word in ["chart", "trend", "plot"])
    needs_sql = bool(student_names) or not needs_graph or needs_chart or "risk" in q
    intent = classify_intent(question)

    sql = heuristic_sql(question) if needs_sql else ""
    graph_query = question if needs_graph else ""

    recommended_tools: list[str] = ["guide_student_query"]
    notes: list[str] = []
    avoid: list[str] = []

    if needs_sql:
        recommended_tools.append("run_sql")
        notes.append(
            "Structured metrics and risk_level (high/medium/low) come from SQLite "
            "view student_risk_summary."
        )
    if needs_graph:
        if student_names:
            recommended_tools.extend(
                [
                    "get_policy_intervention_path",
                    "get_related_risk_factors",
                ]
            )
            notes.append(
                "Use student-specific graph helpers when a student name is known."
            )
        else:
            recommended_tools.append("search_graph_context")
            notes.append(
                "Neo4j holds policy, risk-factor, and intervention paths — not risk_level labels."
            )
            graph_query = graph_topic_terms(question)[0] if graph_topic_terms(question) else graph_query

    if intent == "at_risk_list" or (
        "risk" in q and not student_names and not needs_graph_heuristic(question)
    ):
        avoid.append(
            "Do not use search_graph_context for phrases like 'medium and high risk students' — "
            "that returns no rows. Query student_risk_summary via run_sql instead."
        )
        needs_graph = False
        graph_query = ""

    if intent == "policy_only":
        needs_sql = False
        sql = ""
        needs_graph = True
        notes.append("Policy-only questions should use Neo4j, not SQLite risk summaries.")

    return {
        "question": question,
        "intent": intent,
        "needs_sql": needs_sql,
        "needs_graph": needs_graph,
        "needs_chart": needs_chart,
        "student_names": student_names,
        "sql": sql.strip(),
        "graph_query": graph_query.strip(),
        "recommended_tools": recommended_tools,
        "notes": notes,
        "avoid": avoid,
        "routing_summary": _routing_summary(needs_sql, needs_graph, intent),
    }


def _routing_summary(needs_sql: bool, needs_graph: bool, intent: str) -> str:
    if needs_sql and needs_graph:
        return (
            f"Intent '{intent}': query SQLite for metrics, then Neo4j for policy/intervention context."
        )
    if needs_sql:
        return f"Intent '{intent}': SQLite only (student_risk_summary or related views)."
    if needs_graph:
        return f"Intent '{intent}': Neo4j only (policy, risk factors, interventions)."
    return f"Intent '{intent}': no data tools required."
