import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from student_rag.agents.deterministic import answer_student_question
from student_rag.artifacts import generate_table_or_chart_spec
from student_rag.data.db import get_schema_summary, run_sql
from student_rag.llm import get_llm
from student_rag.data.retrieval import retrieve_notes


MAX_AGENT_ROUNDS = 6


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_schema_summary",
            "description": "Return SQLite tables, views, and columns for the Student Management database.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": (
                "Run one read-only SELECT or WITH query against the Student Management SQLite database. "
                "Prefer analytical views such as student_risk_summary, course_performance_summary, "
                "attendance_trend, assessment_scores, attendance_summary, and fee_summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "A single read-only SELECT or WITH SQL statement.",
                    }
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_notes",
            "description": "Search advising notes, policies, and course descriptions using vector retrieval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for advising notes, policies, and course descriptions.",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Maximum number of chunks to retrieve.",
                        "default": 4,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_artifact",
            "description": (
                "Generate a Markdown table or Vega-Lite chart spec from the latest SQL result. "
                "Use this after run_sql when the user asks for a table, chart, graph, or trend."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The original user question.",
                    },
                    "needs_chart": {
                        "type": "boolean",
                        "description": "True when the user requested a chart, plot, graph, or trend visualization.",
                    },
                },
                "required": ["question", "needs_chart"],
            },
        },
    },
]


SYSTEM_PROMPT = """You are a Student Management analytics agent.

Use the provided tools to answer questions about students, courses, attendance, assessments, fees,
advising notes, course descriptions, and policies.

Rules:
- Use get_schema_summary before writing SQL unless the needed view is already obvious.
- Use run_sql for structured facts, counts, averages, risk levels, fees, grades, and attendance.
- Use retrieve_notes for policies, advising context, explanations, or intervention recommendations.
- Use generate_artifact after run_sql when the user asks for a table, chart, graph, or trend.
- Never invent data. If evidence is missing, say what is missing.
- Keep final answers concise and include practical next actions for risk or intervention questions.
- Do not expose hidden reasoning or thinking tags in the final answer.
"""


def _as_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _tool_args(tool_call: dict[str, Any]) -> dict[str, Any]:
    args = tool_call.get("args", {})
    if isinstance(args, str):
        return json.loads(args) if args else {}
    return args or {}


def answer_with_lmstudio_tools(question: str, max_rounds: int = MAX_AGENT_ROUNDS) -> dict[str, Any]:
    """Run LM Studio's OpenAI-compatible tool-calling loop over student tools."""
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=question),
    ]

    sql_results: list[dict[str, Any]] = []
    retrieved_notes: list[dict[str, Any]] = []
    artifact: dict[str, Any] | None = None
    transcript: list[dict[str, Any]] = []

    try:
        llm = get_llm().bind_tools(TOOLS)
        for _ in range(max_rounds):
            response = llm.invoke(messages)
            messages.append(response)
            tool_calls = getattr(response, "tool_calls", None) or []

            if not tool_calls:
                return {
                    "question": question,
                    "answer": response.content,
                    "sql_results": sql_results,
                    "retrieved_notes": retrieved_notes,
                    "artifact": artifact,
                    "sources": sorted({note["source"] for note in retrieved_notes if note.get("source")}),
                    "transcript": transcript,
                    "mode": "lmstudio_tools",
                }

            for tool_call in tool_calls:
                name = tool_call["name"]
                args = _tool_args(tool_call)
                transcript.append({"tool": name, "args": args})

                if name == "get_schema_summary":
                    result = {"schema": get_schema_summary()}
                elif name == "run_sql":
                    result = run_sql(args["sql"])
                    sql_results.append(result)
                elif name == "retrieve_notes":
                    result = retrieve_notes(args["query"], k=int(args.get("k", 4)))
                    retrieved_notes.extend(result)
                elif name == "generate_artifact":
                    latest_sql = sql_results[-1] if sql_results else {"rows": [], "columns": []}
                    result = generate_table_or_chart_spec(
                        question=args.get("question") or question,
                        sql_result=latest_sql,
                        needs_chart=bool(args.get("needs_chart")),
                    )
                    artifact = result
                else:
                    result = {"error": f"Unknown tool: {name}"}

                messages.append(
                    ToolMessage(
                        content=_as_json(result),
                        tool_call_id=tool_call["id"],
                    )
                )

        fallback = answer_student_question(question)
        fallback["mode"] = "fallback_after_max_rounds"
        fallback["transcript"] = transcript
        return fallback
    except Exception as exc:
        fallback = answer_student_question(question)
        fallback["mode"] = "fallback_after_tool_error"
        fallback["tool_error"] = str(exc)
        fallback["transcript"] = transcript
        return fallback


def main() -> None:
    print("LM Studio Student Tool Agent. Type 'quit' to exit.")
    while True:
        user_question = input("\nAsk a student management question: ").strip()
        if user_question.lower() in {"quit", "exit"}:
            break

        result = answer_with_lmstudio_tools(user_question)
        print(f"\nMode: {result.get('mode')}")
        print("\nAnswer:\n", result["answer"])

        artifact = result.get("artifact")
        if artifact:
            if artifact["type"] == "table":
                print("\nTable:\n", artifact["markdown"])
            else:
                print("\nChart spec:\n", json.dumps(artifact["chart_spec"], indent=2))

        sources = result.get("sources", [])
        if sources:
            print("\nSources:")
            for source in sources:
                print(" -", source)


if __name__ == "__main__":
    main()
