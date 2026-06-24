# Cursor Chat MCP Integration Guide

This guide explains how to ask Student Management questions directly from Cursor Chat.

Cursor can call local tools through MCP. This project exposes the Student Management RAG tools through:

```text
student_rag.mcp.server
```

If Cursor runs on a different machine from the project/data, see `docs/REMOTE_MCP_SERVER_GUIDE.md`.

## 1. Build Local Assets

From the project root:

```powershell
cd D:\rag_assistant
pip install -r requirements.txt
python scripts/build_student_db.py
python scripts/build_student_vectors.py
```

## 2. MCP Server Command

For Cursor, use the launcher script:

```powershell
python D:\rag_assistant\scripts\run_student_mcp_server.py
```

The process should keep running and wait for MCP messages over stdio. Stop it with `Ctrl+C`.

## 3. Cursor MCP Configuration

Add this server to Cursor's MCP configuration.

Recommended project config:

```json
{
  "mcpServers": {
    "student-management-rag": {
      "command": "python",
      "args": [
        "D:\\rag_assistant\\scripts\\run_student_mcp_server.py"
      ]
    }
  }
}
```

If you use a virtual environment, prefer its Python executable:

```json
{
  "mcpServers": {
    "student-management-rag": {
      "command": "D:\\rag_assistant\\.venv\\Scripts\\python.exe",
      "args": [
        "D:\\rag_assistant\\scripts\\run_student_mcp_server.py"
      ]
    }
  }
}
```

After saving the MCP config, reload MCP tools in Cursor if needed.

## 4. Tools Available In Cursor Chat

The MCP server exposes:

- `ask_student_management`
- `get_schema_summary`
- `run_sql`
- `get_at_risk_students`
- `analyze_at_risk_students`
- `get_scholarship_candidates`
- `analyze_scholarship_candidates`
- `retrieve_notes`
- `generate_artifact`

Use `ask_student_management` for normal chat questions. Prefer the `analyze_*` tools only when you want to force a specific workflow.

## 5. Example Cursor Chat Prompts

Risk analysis:

```text
Using the student-management-rag tools, which students are at risk this term and why?
```

Scholarship analysis:

```text
Using the student-management-rag tools, who qualifies for scholarship support based on score, attendance, and fee status?
```

Direct SQL check:

```text
Using the student-management-rag tools, inspect the schema and query student_risk_summary for high-risk students.
```

Policy retrieval:

```text
Using the student-management-rag tools, retrieve notes about scholarship policy and summarize the eligibility criteria.
```

## 6. Answer Quality Checks

For risk answers, make sure Cursor explains both high-risk and medium-risk students.

High-risk triggers:

- `avg_score < 70`
- `attendance_pct < 75`
- `balance_due > 500`

Medium-risk indicators:

- `avg_score < 80`
- `attendance_pct < 85`
- `balance_due > 0`

Important: `risk_reasons` may be empty for medium-risk students. Cursor should still explain medium risk from the metrics and thresholds.

Example:

```text
Noah Patel is medium risk because his average score is below 80, attendance is below 85%, and he has a partial fee balance. He does not meet high-risk thresholds, but he should be monitored.
```

## 7. Troubleshooting

### Cursor Cannot Start The MCP Server

Try the command in a terminal:

```powershell
python D:\rag_assistant\scripts\run_student_mcp_server.py
```

If it fails, run:

```powershell
pip install -r requirements.txt
```

### Package Import Error

Use the launcher script, not `python -m student_rag.mcp.server`, because the launcher inserts `src/` into `sys.path`.

### Empty Or Wrong SQL Result

Ask Cursor to use a high-level tool:

```text
Use ask_student_management instead of writing SQL manually.
```

The schema uses:

- `scholarship_candidate = 1` for yes.
- `risk_level IN ('high', 'medium', 'low')`.
- `term = '2026-Spring'`.

### Cursor Uses Only Structured Data

Ask for the hybrid tool:

```text
Use ask_student_management so you include both SQL rows and retrieved policy/advising context.
```
