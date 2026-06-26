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
LLM_ONLINE_MODE=true
LOG_LEVEL=INFO
```

`LOG_LEVEL=INFO` logs `get_schema_summary` results, LM Studio planning/answer prompts, the raw planning LLM response, and the merged plan in the CLI agent. Use `LOG_LEVEL=WARNING` to reduce noise.

Set `LLM_ONLINE_MODE=false` to skip LM Studio and answer from SQLite + Neo4j evidence only. When `LLM_ONLINE_MODE=true`, the agent requires a working LM Studio connection and reports an error instead of silently falling back.

Start LM Studio, load the model, and start the local server on port `1234`.

## 3. Build Local Assets

Build the SQLite database:

```powershell
python scripts/build_student_db.py
```

Build the Neo4j knowledge graph:

```powershell
python scripts/build_student_kg.py
```

Set Neo4j connection values in `.env` before building:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
```

Generated outputs:

- `student_management.sqlite`

The SQLite file is ignored by git.

## 4. Run The Deterministic Agent

Use this when you want the most reliable local demo path. With `LLM_ONLINE_MODE=true`, LM Studio is required for planning and final synthesis; with `LLM_ONLINE_MODE=false`, it uses deterministic evidence-only planning over SQLite and Neo4j.

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

Use this when you want to type questions directly inside LM Studio Chat. MCP reads SQLite and Neo4j graph tools when the knowledge graph is built.

Prerequisite:

```powershell
python scripts/build_student_db.py
```

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

## 8. Advanced Example Questions

Use these after both `build_student_db.py` and `build_student_kg.py` have been run. Keep the earlier basic examples in sections 4, 5, and 6; these prompts exercise SQLite, Neo4j graph tools, and chart artifacts together.

### Hybrid SQL + Graph

Deterministic agent (`student-agent`) or LM Studio tool agent (`student-lmstudio-agent`):

```text
Which high-risk students have the largest fee balances, and what intervention paths does the knowledge graph recommend for Carlos Reyes?
```

```text
Compare Owen Smith and Carlos Reyes using student_risk_summary metrics and explain the policy/intervention paths from the Neo4j graph.
```

```text
Who qualifies for scholarship support based on score, attendance, and fee status, and what does the Scholarship Support Policy recommend?
```

### Graph-Focused (Neo4j / AutoSchemaKG)

Python agents or MCP chat:

```text
What risk factors are linked to Noah Patel, and which policy and intervention path applies to irregular attendance?
```

```text
For Owen Smith, show the graph path from risk factor to policy to recommended intervention.
```

```text
Which students are advised by Prof. Malik, and what graph context exists for Carlos Reyes?
```

MCP chat (explicit tool use):

```text
Using the student-management-rag tools, call get_policy_intervention_path for Carlos Reyes and summarize the recommended interventions.
```

```text
Using the student-management-rag tools, run analyze_at_risk_students and explain medium-risk students using both SQL metrics and graph_context.
```

### Chart / Artifact Questions

LM Studio tool agent or deterministic agent:

```text
Create a chart of attendance trend by month for high-risk students and explain which students drive the weakest months.
```

```text
Show average grade by course as a table, then chart attendance trend by month for at-risk students.
```

```text
Build a Vega-Lite chart of attendance_pct by month for Owen Smith and Carlos Reyes, and explain the attendance policy thresholds.
```

MCP chat:

```text
Using the student-management-rag tools, query attendance_trend for high-risk students, call generate_artifact with needs_chart=true, and describe the trend.
```

### Multi-Step Showcase Prompts

These are good demo questions for the full showcase:

```text
Which students are at risk this term, why do metrics flag them, and what policy/intervention paths does the knowledge graph suggest for the highest-risk cases?
```

```text
Show course weak areas from SQLite, identify students most at risk in the weakest courses, and pull graph evidence for recommended interventions.
```

```text
Who has overdue balances above 500, which financial-hold policy applies, and what intervention does the graph recommend?
```

## 9. Quick Validation Commands

Check Python compilation:

```powershell
python -m py_compile src/student_rag/*.py src/student_rag/data/*.py src/student_rag/kg/*.py src/student_rag/agents/*.py src/student_rag/mcp/*.py eval_student_run.py scripts/build_student_db.py scripts/build_student_kg.py
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

## 10. Common Problems

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

If you intentionally want to run without LM Studio, set:

```env
LLM_ONLINE_MODE=false
```

If `LLM_ONLINE_MODE=true`, timeout and connection failures are shown as errors instead of being hidden by offline fallback behavior.

### Neo4j Unavailable

Start Neo4j and rebuild the graph:

```powershell
python scripts/build_student_kg.py
```

Default Bolt port is `7687`, not `7685`. For local use on the same machine, you usually do not need a Windows Firewall rule; connection refused usually means Neo4j is not running yet.

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

## 10. Call tree

student_rag.agents.deterministic.main()
└─ answer_student_question(question)
├─ plan_question(question)
│  ├─ get_schema_summary()
│  │  └─ student_rag.data.db.get_schema_summary()
│  ├─ get_llm()
│  │  └─ ChatOpenAI(base_url=LMSTUDIO_BASE_URL, model=LMSTUDIO_MODEL)
│  └─ LM Studio API call
│     └─ returns JSON plan:
│        ├─ needs_sql
│        ├─ needs_graph
│        ├─ needs_chart
│        ├─ graph_query
│        └─ sql
│
├─ decompose_query_request(plan)
│  └─ builds internal step list
│
├─ if needs_sql:
│  └─ run_sql(plan["sql"])
│     └─ student_rag.data.db.run_sql()
│        └─ SQLite: student_management.sqlite
│
├─ if needs_graph:
│  └─ get_graph_evidence(question, graph_query)
│     ├─ extract student names from question
│     ├─ get_related_risk_factors(student_name)
│     │  └─ run_read_only_cypher()
│     │     └─ Neo4j: StudentDB
│     ├─ get_policy_intervention_path(student_name)
│     │  └─ run_read_only_cypher()
│     │     └─ Neo4j: StudentDB
│     └─ search_graph_context(topic/query)
│        └─ run_read_only_cypher()
│           └─ Neo4j: StudentDB
│
├─ replan_if_needed(question, plan, sql_result, graph_context)
│  └─ if SQL returned no rows:
│     └─ run fallback SQL
│
├─ generate_table_or_chart_spec(question, sql_result, needs_chart)
│  └─ returns:
│     ├─ Markdown table, or
│     └─ Vega-Lite chart spec
│
├─ answer_from_evidence(question, plan, sql_result, graph_context, artifact)
│  ├─ get_llm()
│  └─ LM Studio API call
│     └─ final natural-language answer from evidence JSON
│
└─ return result dict
├─ question
├─ plan
├─ steps
├─ sql_result
├─ graph_context
├─ artifact
├─ answer
├─ sources
└─ mode = "llm"