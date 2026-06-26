from typing import Any


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
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
        "markdown": markdown_table(rows, columns),
    }


def graph_artifact_from_context(graph_context: dict[str, Any] | None) -> dict[str, Any]:
    """Build a Markdown table from Neo4j graph evidence for CLI display."""
    if not graph_context:
        return {"type": "graph_table", "markdown": "", "rows": [], "columns": []}

    path_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []

    for student_block in graph_context.get("students", []):
        student_name = student_block.get("student_name", "")
        for row in student_block.get("risk_factors", {}).get("risk_factors", []):
            risk_rows.append(
                {
                    "student_name": row.get("student_name") or student_name,
                    "risk_factor": row.get("risk_factor", ""),
                    "evidence_text": row.get("evidence_text", ""),
                }
            )
        for row in student_block.get("policy_paths", {}).get("paths", []):
            path_rows.append(
                {
                    "student_name": row.get("student_name") or student_name,
                    "risk_factor": row.get("risk_factor", ""),
                    "policy": row.get("policy", ""),
                    "intervention": row.get("intervention", ""),
                }
            )

    for match_group in graph_context.get("topic_matches", []):
        topic = match_group.get("query", "")
        for row in match_group.get("matches", []):
            if row.get("relation") != "TRIGGERS_POLICY":
                continue
            candidate = {
                "student_name": "",
                "risk_factor": row.get("name", topic),
                "policy": row.get("related_name", ""),
                "intervention": "",
            }
            if any(
                candidate["risk_factor"] == existing.get("risk_factor")
                and candidate["policy"] == existing.get("policy")
                for existing in path_rows
            ):
                continue
            path_rows.append(candidate)

    sections: list[str] = []
    if risk_rows:
        sections.append("Risk factors")
        sections.append(markdown_table(risk_rows, ["student_name", "risk_factor", "evidence_text"]))
    if path_rows:
        if sections:
            sections.append("")
        sections.append("Policy and intervention paths")
        sections.append(markdown_table(path_rows, ["student_name", "risk_factor", "policy", "intervention"]))

    return {
        "type": "graph_table",
        "markdown": "\n".join(sections),
        "risk_rows": risk_rows,
        "path_rows": path_rows,
    }
