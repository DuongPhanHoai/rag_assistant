# student_agent.py
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_openai import ChatOpenAI

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

from scripts.build_student_db import DB_PATH, build_database
from scripts.build_student_vectors import EMBEDDING_MODEL, VECTOR_DB_DIR, build_student_vectorstore


load_dotenv()

LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "lmstudio")
LMSTUDIO_TIMEOUT_SECONDS = float(os.getenv("LMSTUDIO_TIMEOUT_SECONDS", "10"))

MAX_SQL_ROWS = 50
BLOCKED_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|vacuum|pragma)\b",
    re.IGNORECASE,
)


def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=LMSTUDIO_BASE_URL,
        api_key="not-needed",
        model=LMSTUDIO_MODEL,
        temperature=0,
        timeout=LMSTUDIO_TIMEOUT_SECONDS,
    )


def ensure_student_assets() -> None:
    if not Path(DB_PATH).exists():
        build_database()
    if not Path(VECTOR_DB_DIR).exists():
        build_student_vectorstore()


def get_student_vectorstore() -> Chroma:
    ensure_student_assets()
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    return Chroma(
        embedding_function=embeddings,
        persist_directory=str(VECTOR_DB_DIR),
    )


def get_schema_summary() -> str:
    ensure_student_assets()
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT name, type
            FROM sqlite_master
            WHERE type IN ('table', 'view')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()

        lines = []
        for name, object_type in rows:
            columns = conn.execute(f"PRAGMA table_info({name})").fetchall()
            column_names = ", ".join(column[1] for column in columns)
            lines.append(f"- {object_type} {name}: {column_names}")
        return "\n".join(lines)
    finally:
        conn.close()


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response")
    return json.loads(match.group(0))


def _heuristic_sql(question: str) -> str:
    q = question.lower()

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

    return """
    SELECT student_name, program, advisor, avg_score, attendance_pct, balance_due,
           risk_level, risk_reasons, scholarship_candidate
    FROM student_risk_summary
    ORDER BY
        CASE risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
        avg_score ASC
    """


def _fallback_plan(question: str) -> dict[str, Any]:
    q = question.lower()
    needs_chart = any(word in q for word in ["chart", "trend", "plot", "graph"])
    return {
        "question": question,
        "reasoning": "Fallback plan based on keywords.",
        "needs_sql": True,
        "needs_vector": True,
        "needs_chart": needs_chart,
        "search_query": question,
        "sql": _heuristic_sql(question),
    }


def plan_question(question: str) -> dict[str, Any]:
    schema = get_schema_summary()
    prompt = f"""
You are planning a small agentic RAG workflow over a Student Management SQLite database and student support documents.

Return only JSON with these keys:
- reasoning: short explanation
- needs_sql: boolean
- needs_vector: boolean
- needs_chart: boolean
- search_query: text to use for vector retrieval
- sql: a single read-only SELECT or WITH query, or an empty string

Prefer the views student_risk_summary, course_performance_summary, attendance_trend, assessment_scores,
attendance_summary, and fee_summary when they answer the question.

Schema:
{schema}

Question:
{question}
"""
    try:
        response = get_llm().invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        plan = _extract_json(content)
    except Exception:
        return _fallback_plan(question)

    fallback = _fallback_plan(question)
    return {
        "question": question,
        "reasoning": str(plan.get("reasoning") or fallback["reasoning"]),
        "needs_sql": bool(plan.get("needs_sql", fallback["needs_sql"])),
        "needs_vector": bool(plan.get("needs_vector", fallback["needs_vector"])),
        "needs_chart": bool(plan.get("needs_chart", fallback["needs_chart"])),
        "search_query": str(plan.get("search_query") or fallback["search_query"]),
        "sql": str(plan.get("sql") or fallback["sql"]),
    }


def decompose_query_request(plan: dict[str, Any]) -> list[dict[str, str]]:
    steps = [{"step": "plan", "detail": plan.get("reasoning", "")}]
    if plan.get("needs_sql"):
        steps.append({"step": "query_structured_data", "detail": plan.get("sql", "")})
    if plan.get("needs_vector"):
        steps.append({"step": "query_embeddings", "detail": plan.get("search_query", "")})
    if plan.get("needs_chart"):
        steps.append({"step": "generate_chart", "detail": "Create a Vega-Lite chart spec from SQL rows."})
    else:
        steps.append({"step": "generate_table", "detail": "Create a compact Markdown table from SQL rows."})
    steps.append({"step": "replan", "detail": "Check whether evidence is missing and run a fallback query if needed."})
    steps.append({"step": "answer", "detail": "Synthesize SQL evidence, retrieved notes, and sources."})
    return steps


def validate_read_only_sql(sql: str) -> str:
    cleaned = sql.strip()
    if not cleaned:
        raise ValueError("SQL is empty")

    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()
    if ";" in cleaned:
        raise ValueError("Only one SQL statement is allowed")
    if BLOCKED_SQL.search(cleaned):
        raise ValueError("Only read-only SELECT/WITH SQL is allowed")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise ValueError("SQL must start with SELECT or WITH")

    return cleaned


def run_sql(sql: str, limit: int = MAX_SQL_ROWS) -> dict[str, Any]:
    ensure_student_assets()
    cleaned = validate_read_only_sql(sql)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(cleaned)
        rows = cursor.fetchmany(limit + 1)
        columns = [description[0] for description in cursor.description or []]
        limited = len(rows) > limit
        rows = rows[:limit]
        return {
            "sql": cleaned,
            "columns": columns,
            "rows": [dict(row) for row in rows],
            "row_count": len(rows),
            "limited": limited,
        }
    finally:
        conn.close()


def retrieve_notes(query: str, k: int = 4) -> list[dict[str, Any]]:
    vectordb = get_student_vectorstore()
    docs = vectordb.similarity_search(query, k=k)
    return [
        {
            "source": doc.metadata.get("source", ""),
            "content": doc.page_content,
        }
        for doc in docs
    ]


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "No rows returned."

    display_columns = columns[:8]
    header = "| " + " | ".join(display_columns) + " |"
    separator = "| " + " | ".join(["---"] * len(display_columns)) + " |"
    body = []
    for row in rows[:10]:
        values = [str(row.get(column, "")) for column in display_columns]
        body.append("| " + " | ".join(values) + " |")
    return "\n".join([header, separator, *body])


def generate_table_or_chart_spec(question: str, sql_result: dict[str, Any], needs_chart: bool) -> dict[str, Any]:
    rows = sql_result.get("rows", [])
    columns = sql_result.get("columns", [])
    if needs_chart and rows:
        x_field = "month" if "month" in columns else columns[0]
        y_field = "attendance_pct" if "attendance_pct" in columns else columns[-1]
        color_field = "student_name" if "student_name" in columns else None
        encoding = {
            "x": {"field": x_field, "type": "ordinal"},
            "y": {"field": y_field, "type": "quantitative"},
        }
        if color_field:
            encoding["color"] = {"field": color_field, "type": "nominal"}

        return {
            "type": "chart",
            "chart_spec": {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "description": question,
                "data": {"values": rows},
                "mark": "line",
                "encoding": encoding,
            },
        }

    return {
        "type": "table",
        "markdown": _markdown_table(rows, columns),
    }


def replan_if_needed(
    question: str,
    plan: dict[str, Any],
    sql_result: dict[str, Any] | None,
    notes: list[dict[str, Any]],
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


def _fallback_answer(
    question: str,
    sql_result: dict[str, Any] | None,
    notes: list[dict[str, Any]],
    artifact: dict[str, Any],
) -> str:
    lines = [f"Question: {question}", ""]
    if sql_result and sql_result.get("rows"):
        lines.append("Structured evidence:")
        lines.append(_markdown_table(sql_result["rows"], sql_result["columns"]))
        lines.append("")
    if notes:
        lines.append("Retrieved notes:")
        for note in notes[:3]:
            first_line = note["content"].strip().splitlines()[0]
            lines.append(f"- {first_line} ({note['source']})")
        lines.append("")
    if artifact["type"] == "chart":
        lines.append("A Vega-Lite chart spec is included in the result under `artifact.chart_spec`.")
    return "\n".join(lines).strip()


def answer_from_evidence(
    question: str,
    plan: dict[str, Any],
    sql_result: dict[str, Any] | None,
    notes: list[dict[str, Any]],
    artifact: dict[str, Any],
) -> str:
    evidence = {
        "plan": plan,
        "sql_result": sql_result,
        "retrieved_notes": notes,
        "artifact": artifact,
    }
    prompt = f"""
Answer the student management question using only the evidence below.

Rules:
- Be concise and factual.
- Mention when the answer depends on both structured data and advising or policy notes.
- If a chart spec is included, describe what the chart shows.
- Include practical next actions when the question is about risk or intervention.

Question:
{question}

Evidence JSON:
{json.dumps(evidence, ensure_ascii=False, indent=2)}
"""
    try:
        response = get_llm().invoke(prompt)
        return response.content if hasattr(response, "content") else str(response)
    except Exception:
        return _fallback_answer(question, sql_result, notes, artifact)


def answer_student_question(question: str) -> dict[str, Any]:
    plan = plan_question(question)
    steps = decompose_query_request(plan)

    sql_result = run_sql(plan["sql"]) if plan.get("needs_sql") else None
    notes = retrieve_notes(plan.get("search_query") or question) if plan.get("needs_vector") else []
    plan, sql_result = replan_if_needed(question, plan, sql_result, notes)

    artifact = generate_table_or_chart_spec(
        question=question,
        sql_result=sql_result or {"rows": [], "columns": []},
        needs_chart=bool(plan.get("needs_chart")),
    )
    answer = answer_from_evidence(question, plan, sql_result, notes, artifact)
    sources = sorted({note["source"] for note in notes if note.get("source")})

    return {
        "question": question,
        "plan": plan,
        "steps": steps,
        "sql_result": sql_result,
        "retrieved_notes": notes,
        "artifact": artifact,
        "answer": answer,
        "sources": sources,
    }


if __name__ == "__main__":
    print("Student Agentic RAG sample. Type 'quit' to exit.")
    while True:
        user_question = input("\nAsk a student management question: ").strip()
        if user_question.lower() in {"quit", "exit"}:
            break
        try:
            result = answer_student_question(user_question)
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
