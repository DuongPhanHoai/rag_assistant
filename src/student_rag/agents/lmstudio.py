import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from student_rag.agents.deterministic import answer_student_question
from student_rag.artifacts import generate_table_or_chart_spec
from student_rag.data.db import get_schema_summary, run_sql
from student_rag.kg.neo4j_store import (
    get_policy_intervention_path,
    get_related_risk_factors,
    get_student_graph_context,
    query_knowledge_graph,
)
from student_rag.logging_config import configure_logging
from student_rag.llm import get_llm
from student_rag.paths import LLM_ONLINE_MODE


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
            "name": "get_student_graph_context",
            "description": (
                "Return Neo4j graph context for one student from the AutoSchemaKG-built knowledge graph."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "student_name": {
                        "type": "string",
                        "description": "Full student name, for example Carlos Reyes.",
                    }
                },
                "required": ["student_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_policy_intervention_path",
            "description": (
                "Return policy and intervention paths for a student based on risk factors in Neo4j."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "student_name": {
                        "type": "string",
                        "description": "Full student name, for example Owen Smith.",
                    }
                },
                "required": ["student_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_related_risk_factors",
            "description": "Return risk factors linked to a student in the Neo4j knowledge graph.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_name": {
                        "type": "string",
                        "description": "Full student name.",
                    }
                },
                "required": ["student_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_knowledge_graph",
            "description": (
                "Run one read-only Cypher query against the Neo4j knowledge graph populated by AutoSchemaKG."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cypher": {
                        "type": "string",
                        "description": "A read-only Cypher query using MATCH/RETURN.",
                    }
                },
                "required": ["cypher"],
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
policies, interventions, and advising context.

Rules:
- Use get_schema_summary before writing SQL unless the needed view is already obvious.
- Use run_sql for structured facts, counts, averages, risk levels, fees, grades, and attendance.
- Use Neo4j graph tools for policies, intervention paths, risk factors, and relationship evidence.
- The Neo4j graph is built offline from markdown docs using AutoSchemaKG.
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


def _graph_sources(graph_results: list[dict[str, Any]]) -> list[str]:
    sources: set[str] = set()
    for result in graph_results:
        for key in ("context", "paths", "risk_factors", "rows", "matches"):
            for row in result.get(key, []) or []:
                source_doc = row.get("source_doc")
                if source_doc:
                    sources.add(source_doc)
    return sorted(sources)


def answer_with_lmstudio_tools(question: str, max_rounds: int = MAX_AGENT_ROUNDS) -> dict[str, Any]:
    """Run LM Studio's OpenAI-compatible tool-calling loop over student tools."""
    if not LLM_ONLINE_MODE:
        fallback = answer_student_question(question)
        fallback["mode"] = "offline_evidence"
        return fallback

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=question),
    ]

    sql_results: list[dict[str, Any]] = []
    graph_results: list[dict[str, Any]] = []
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
                    "graph_results": graph_results,
                    "artifact": artifact,
                    "sources": _graph_sources(graph_results),
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
                elif name == "get_student_graph_context":
                    result = get_student_graph_context(args["student_name"])
                    graph_results.append(result)
                elif name == "get_policy_intervention_path":
                    result = get_policy_intervention_path(args["student_name"])
                    graph_results.append(result)
                elif name == "get_related_risk_factors":
                    result = get_related_risk_factors(args["student_name"])
                    graph_results.append(result)
                elif name == "query_knowledge_graph":
                    result = query_knowledge_graph(args["cypher"])
                    graph_results.append(result)
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

        raise RuntimeError(
            "LM Studio tool loop reached max rounds without a final answer."
        )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"LM Studio connection failed during tool loop: {exc}") from exc


def main() -> None:
    configure_logging()
    print("LM Studio Student Tool Agent. Type 'quit' to exit.")
    while True:
        user_question = input("\nAsk a student management question: ").strip()
        if user_question.lower() in {"quit", "exit"}:
            break

        try:
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
        except Exception as exc:
            print("Error:", exc)


if __name__ == "__main__":
    main()
