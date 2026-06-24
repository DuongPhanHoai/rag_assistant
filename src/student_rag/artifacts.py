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
