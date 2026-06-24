# LM Studio Chat Agent Integration Guide

This guide explains how to ask Student Management questions directly inside the LM Studio Chat UI.

## 1. Integration Modes

There are two possible integrations:

- **LM Studio Chat UI with MCP**: you chat inside LM Studio, and LM Studio calls this project as a local MCP tool server.
- **Python API agent**: you run `python -m student_rag.lmstudio_agent`, and that Python process calls LM Studio's OpenAI-compatible API.

If your goal is to type questions in LM Studio Chat, use **LM Studio Chat UI with MCP**.

The chat-first flow is:

```text
LM Studio Chat
  -> Local model decides it needs a tool
  -> LM Studio calls student-mcp-server
  -> Python queries SQLite or Chroma
  -> Tool result returns to LM Studio Chat
  -> Model writes the final answer
```

## 2. Recommended Model

For lightweight testing, this model is acceptable:

```env
qwen/qwen3-4b-thinking-2507
```

It is small and good at reasoning, but because it is a thinking model, strict tool calling may occasionally be unstable. If tool calls are unreliable, use a non-thinking instruct or coder model, such as a Qwen instruct/coder model around 7B if your machine can run it.

## 3. Install And Build Local Assets

Install dependencies:

```powershell
pip install -r requirements.txt
```

Build SQLite:

```powershell
python scripts/build_student_db.py
```

Build Chroma embeddings:

```powershell
python scripts/build_student_vectors.py
```

## 4. Configure LM Studio Chat MCP

LM Studio can act as an MCP host. Add this project as a local MCP server.

In LM Studio:

1. Open Chat.
2. Open the right-side Program or MCP tools panel.
3. Click `Install`.
4. Click `Edit mcp.json`.
5. Add the `student-management-rag` server.

Recommended config after running `pip install -r requirements.txt`:

```json
{
  "mcpServers": {
    "student-management-rag": {
      "command": "student-mcp-server",
      "args": []
    }
  }
}
```

If LM Studio cannot find `student-mcp-server` on Windows, use Python directly:

```json
{
  "mcpServers": {
    "student-management-rag": {
      "command": "python",
      "args": ["-m", "student_rag.mcp_server"]
    }
  }
}
```

If that still cannot find the package, use the Python executable from your virtual environment and make sure you installed the project with `pip install -r requirements.txt`.

## 5. Chat From LM Studio

After saving `mcp.json`, LM Studio should load the MCP server. Enable the `student-management-rag` tools in the chat if they are not already enabled.

Try:

```text
Using the student-management-rag tools, which students are at risk this term and why?
```

```text
Using the student-management-rag tools, who qualifies for scholarship support based on GPA, attendance, and fee status?
```

```text
Using the student-management-rag tools, create a chart of attendance trend by month for at-risk students.
```

## 6. MCP Tools Exposed To LM Studio Chat

`student_rag.mcp_server` exposes these tools:

### `get_schema_summary`

Returns available SQLite tables, views, and columns.

Use case: helps the model write valid SQL.

### `run_sql`

Runs one validated read-only SQL query.

Safety rules:

- Must start with `SELECT` or `WITH`.
- Only one statement is allowed.
- Mutating SQL keywords are rejected.

Important value hints:

- `student_risk_summary.risk_level` uses text values: `high`, `medium`, `low`.
- `student_risk_summary.scholarship_candidate` uses integer values: `1` means yes, `0` means no.
- Do not filter `scholarship_candidate = 'yes'`; use `scholarship_candidate = 1`.
- `student_risk_summary.term` uses values such as `2026-Spring`; there is no `current_term` value.

### `get_at_risk_students`

Returns high-risk and medium-risk students with grades, attendance, balance due, risk level, and risk reasons.

Use case: safer than asking the model to invent a risk SQL query.

### `get_scholarship_candidates`

Returns students who qualify for scholarship support using the correct condition:

```sql
scholarship_candidate = 1
```

Use case: safer than asking the model to guess whether the flag is `yes`, `true`, or `1`.

### `retrieve_notes`

Searches the Chroma vector store for advising notes, policies, and course descriptions.

Use case: explains why a student is at risk, what policy applies, or what intervention is recommended.

### `generate_artifact`

Creates either:

- Markdown table.
- Vega-Lite chart spec.

Use case: table/chart/trend questions.

## 7. Optional: Python API Agent

Use this mode when you want Python to drive the agent loop and call LM Studio through the OpenAI-compatible API.

LM Studio should expose:

```text
http://localhost:1234/v1
```

Create or update `.env`:

```env
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=qwen/qwen3-4b-thinking-2507
LMSTUDIO_TIMEOUT_SECONDS=30
```

Run:

```powershell
python -m student_rag.lmstudio_agent
```

Or:

```powershell
student-lmstudio-agent
```

## 8. Recommended Prompt Pattern

Ask natural questions. Mention the tool server name if LM Studio does not choose it automatically.

Good examples:

- `Using the student-management-rag tools, call get_at_risk_students and explain who is at risk and why.`
- `Using the student-management-rag tools, show course performance by average score and attendance.`
- `Using the student-management-rag tools, call get_scholarship_candidates and explain the policy.`
- `Using the student-management-rag tools, create an attendance trend chart for high-risk students.`

Avoid asking the model to write directly to the database. This sample intentionally supports read-only analysis.

## 9. Troubleshooting

### MCP Server Does Not Appear

Check:

- You saved LM Studio's `mcp.json`.
- You installed dependencies with `pip install -r requirements.txt`.
- `student-mcp-server` works in a normal terminal.
- If using Windows and PATH is a problem, use the full path to your Python executable in `mcp.json`.

### MCP Tool Fails To Start

Try this from a terminal:

```powershell
student-mcp-server
```

The command should stay running because it waits for MCP messages over stdio. Stop it with `Ctrl+C`.

### Model Does Not Use Tools

Try a more explicit prompt:

```text
Use the student-management-rag MCP tools. First inspect the schema, then query the data and retrieve relevant notes before answering.
```

### Empty Scholarship Result

If the model called:

```sql
WHERE scholarship_candidate = 'yes'
```

the result will be empty because `scholarship_candidate` is an integer flag. Ask:

```text
Using the student-management-rag tools, call get_scholarship_candidates.
```

Or use:

```sql
WHERE scholarship_candidate = 1
```

### Tool Calls Are Weird Or Repeated

This can happen with thinking models. Try:

- Start a fresh LM Studio chat session.
- Use a non-thinking Qwen instruct/coder model.
- Keep prompts direct and avoid asking about tool-call syntax.

### Chroma Or Embedding Errors

Rebuild the vector store:

```powershell
python scripts/build_student_vectors.py
```

### SQLite Errors

Rebuild the database:

```powershell
python scripts/build_student_db.py
```

## 10. Where To Extend Next

Good next extensions:

- Add more SQLite views for common analytics.
- Add more advising/policy documents.
- Add chart rendering from the Vega-Lite spec.
- Add tests for SQL validation and common questions.
