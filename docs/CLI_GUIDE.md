# CLI Guide

This guide shows how to run the Student Management Agentic RAG sample from a terminal.

Commands below use PowerShell on Windows from the project root:

```powershell
cd D:\rag_assistant
```

## 1. Install Dependencies

Create and activate a virtual environment if you want an isolated setup:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the project and dependencies:

```powershell
pip install -r requirements.txt
```

This installs the package in editable mode because `requirements.txt` contains:

```text
-e .
```

## 2. Configure LM Studio

Create or update `.env`:

```env
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=qwen/qwen3-4b-thinking-2507
LMSTUDIO_TIMEOUT_SECONDS=30
```

Start LM Studio, load the model, and start the local server on port `1234`.

## 3. Build Local Assets

Build the SQLite database:

```powershell
python scripts/build_student_db.py
```

Build the Chroma vector store:

```powershell
python scripts/build_student_vectors.py
```

Generated outputs:

- `student_management.sqlite`
- `chroma_student_db/`

Both are ignored by git.

## 4. Run The Deterministic Agent

Use this when you want the most reliable local demo path. It uses deterministic fallback planning if LM Studio is slow or unavailable.

```powershell
python -m student_rag.agents.deterministic
```

Or use the installed console script:

```powershell
student-agent
```

Example question:

```text
Which students are at risk this term and why?
```

## 5. Run The LM Studio Tool Agent

Use this when you want Python to call LM Studio and let the model choose tools through the OpenAI-compatible tool-calling API.

```powershell
python -m student_rag.agents.lmstudio
```

Or:

```powershell
student-lmstudio-agent
```

Example question:

```text
Create a chart of attendance trend by month for at-risk students.
```

## 6. Run The MCP Server For LM Studio Chat

Use this when you want to type questions directly inside LM Studio Chat.

First test that the MCP server starts:

```powershell
student-mcp-server
```

The process should stay running and wait for MCP messages over stdio. Stop it with `Ctrl+C`.

In LM Studio `mcp.json`, configure:

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

If LM Studio cannot find the command, use Python directly:

```json
{
  "mcpServers": {
    "student-management-rag": {
      "command": "python",
      "args": ["-m", "student_rag.mcp.server"]
    }
  }
}
```

Then ask in LM Studio Chat:

```text
Using the student-management-rag tools, which students are at risk this term and why?
```

## 7. Run Evaluation

Run the fixed student question set:

```powershell
python eval_student_run.py
```

Output:

```text
eval/student_results.jsonl
```

This file is ignored by git.

## 8. Quick Validation Commands

Check Python compilation:

```powershell
python -m py_compile src/student_rag/*.py src/student_rag/data/*.py src/student_rag/agents/*.py src/student_rag/mcp/*.py eval_student_run.py scripts/build_student_db.py scripts/build_student_vectors.py
```

Check the risk summary directly:

```powershell
python -c "import sys,json; sys.path.insert(0, r'D:\rag_assistant\src'); from student_rag.data.db import run_sql; print(json.dumps(run_sql('SELECT student_name, avg_score, attendance_pct, balance_due, risk_level, risk_reasons FROM student_risk_summary ORDER BY avg_score'), indent=2))"
```

Expected high-risk students include:

- Owen Smith
- Carlos Reyes
- Lina Garcia

Expected medium-risk students include:

- Noah Patel
- Minh Nguyen

When reviewing answers, do not treat empty `risk_reasons` as "no reason" for medium-risk students. Medium risk is inferred from metrics such as average score below `80`, attendance below `85%`, or a partial fee balance.

## 9. Common Problems

### `ModuleNotFoundError: student_rag`

Run:

```powershell
pip install -r requirements.txt
```

Or temporarily set:

```powershell
$env:PYTHONPATH='src'
```

### LM Studio Timeout

Increase timeout in `.env`:

```env
LMSTUDIO_TIMEOUT_SECONDS=60
```

### Chroma Or Embedding Error

Rebuild vectors:

```powershell
python scripts/build_student_vectors.py
```

### SQLite Data Looks Wrong

Rebuild the database:

```powershell
python scripts/build_student_db.py
```

### LM Studio Chat Gives Wrong SQL Answer

Ask it to use the MCP tools explicitly:

```text
Using the student-management-rag tools, inspect the schema, query student_risk_summary, and answer which students are at risk this term and why.
```

For reliable terminal output, prefer:

```powershell
python -m student_rag.agents.deterministic
```
