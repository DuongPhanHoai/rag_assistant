# MCP Server Modes

The Student Management MCP server supports two modes via `STUDENT_MCP_MODE` in `.env` or the MCP client `env` block.

## Mode comparison

| | **Mode 1: `proxy`** | **Mode 2: `tools`** (default) |
|---|---------------------|-------------------------------|
| **Who plans?** | Our agent (`answer_student_question`) | Host model (Cursor / LM Studio Chat) |
| **Who answers?** | Our agent (LLM step 2 when online) | Host model synthesizes from tool results |
| **Tools exposed** | `ask_student_agent` | SQLite + Neo4j schema + read-only data tools |
| **Like** | CLI agent | LM Studio tool loop with schemas |

---

## Mode 1 — `proxy` (forward to agent)

Forward the **whole question** to the same pipeline as the CLI agent:

```text
Question → plan_question → run_sql / get_graph_evidence → artifact → answer_from_evidence
```

### Tool

- **`ask_student_agent(question)`** — returns full JSON: `answer`, `plan`, `sources`, `sql_result`, `graph_context`, `artifact`, etc.

### Configure

```json
{
  "mcpServers": {
    "student-management-rag": {
      "command": "python",
      "args": ["D:\\rag_assistant\\scripts\\run_student_mcp_server.py"],
      "env": {
        "STUDENT_MCP_MODE": "proxy",
        "LLM_ONLINE_MODE": "true"
      }
    }
  }
}
```

Requires LM Studio (or configured LLM) when `LLM_ONLINE_MODE=true`.

### Timeouts (important)

`ask_student_agent` runs **two LLM calls** (plan + answer). With thinking models this often takes **1–3 minutes**. Many MCP hosts (Cursor / LM Studio Chat) **cancel tool calls after ~60–120 seconds**, which looks like a timeout even when the server is still working.

**If you see repeated timeout errors:**

1. Call **`check_agent_ready`** first (fast sanity check).
2. Switch to **`tools` mode** (recommended for MCP chat) — smaller, faster tool calls.
3. Or use a **faster model** in LM Studio (avoid thinking models for proxy mode).
4. Increase in `.env`:
   ```env
   LMSTUDIO_TIMEOUT_SECONDS=120
   MCP_PROXY_LLM_TIMEOUT_SECONDS=180
   ```
5. Prefer **local stdio MCP** over remote HTTP if latency is an issue.
6. Kill duplicate servers if port 8765 is busy (Windows: `netstat -ano | findstr :8765` then `taskkill /PID <pid> /F`).

### Example prompt (Cursor / LM Studio)

```text
Use ask_student_agent to answer: Which students are at high risk and what intervention applies to Noah Patel?
```

---

## Mode 2 — `tools` (schema + low-level tools)

Expose **schemas** and **read-only tools** so the **host model** plans SQL/Cypher and writes the answer.

### Schema tools

| Tool | Returns |
|------|---------|
| `get_sqlite_schema()` | Tables, views, columns |
| `get_neo4j_schema()` | Node labels, relationship types, path patterns |
| `get_schema_summary()` | Alias for `get_sqlite_schema()` |

### Data tools

| Tool | Purpose |
|------|---------|
| **`guide_student_query(question)`** | **Call first.** Routes SQLite vs Neo4j, runs the right queries, returns evidence |
| `run_sql(sql)` | Read-only SQLite SELECT/WITH |
| `search_graph_context(query)` | Keyword search over Neo4j policy/risk evidence (not risk_level lists) |
| `query_knowledge_graph(cypher)` | Read-only Cypher |
| `get_student_graph_context(student_name)` | One student's graph neighborhood |
| `get_policy_intervention_path(student_name)` | Risk → policy → intervention paths |
| `get_related_risk_factors(student_name)` | Student risk factors |
| `generate_artifact(question, sql_result_json, needs_chart?)` | Table or Vega-Lite chart spec |

### Configure (default)

```json
{
  "mcpServers": {
    "student-management-rag": {
      "command": "python",
      "args": ["D:\\rag_assistant\\scripts\\run_student_mcp_server.py"],
      "env": {
        "STUDENT_MCP_MODE": "tools"
      }
    }
  }
}
```

### Example prompt

```text
Use guide_student_query from student-management-rag, then answer from the returned evidence.
```

For low-level control you can still call `get_sqlite_schema`, `run_sql`, and graph helpers directly.

---

## Shared

- **`get_mcp_mode()`** — returns active mode and tool list
- **`/health`** — HTTP remote server reports `"mcp_mode": "proxy"` or `"tools"`

## Remote MCP (HTTP / SSE)

Run on **Machine A** (hosts SQLite, Neo4j, and optional LM Studio for proxy mode). Connect from **Machine B** (Cursor / LM Studio) via URL.

### Start remote server — Mode 2 (`tools`)

```powershell
cd D:\rag_assistant
python scripts/build_student_db.py
python scripts/build_student_kg.py
python scripts/run_student_mcp_http_server.py --host 0.0.0.0 --port 8765 --mode tools --transport streamable-http --unsafe-disable-dns-rebinding-protection
```

### Start remote server — Mode 1 (`proxy`)

Requires LM Studio on Machine A when `LLM_ONLINE_MODE=true`:

```powershell
$env:LLM_ONLINE_MODE = "true"
python scripts/run_student_mcp_http_server.py --host 0.0.0.0 --port 8765 --mode proxy --transport streamable-http --unsafe-disable-dns-rebinding-protection
```

Or set `STUDENT_MCP_MODE=proxy` in `.env` on Machine A and omit `--mode`.

### Verify

```text
GET http://MACHINE_A_IP:8765/health
→ {"status":"ok","mcp_mode":"tools"|"proxy","transport":"http",...}
```

### Client `mcp.json` (Machine B)

**Remote tools mode:**

```json
{
  "mcpServers": {
    "student-management-rag": {
      "url": "http://MACHINE_A_IP:8765/mcp"
    }
  }
}
```

**Remote proxy mode** — same URL; server must be started with `--mode proxy`:

```json
{
  "mcpServers": {
    "student-management-rag": {
      "url": "http://MACHINE_A_IP:8765/mcp"
    }
  }
}
```

SSE alternative: `--transport sse` → client URL `http://MACHINE_A_IP:8765/sse`

Full firewall and troubleshooting: [REMOTE_MCP_SERVER_GUIDE.md](REMOTE_MCP_SERVER_GUIDE.md)

---

## Local run commands

```powershell
# Default (tools)
python scripts/run_student_mcp_server.py

# Proxy mode
$env:STUDENT_MCP_MODE = "proxy"
python scripts/run_student_mcp_server.py

# Remote HTTP (either mode via env)
$env:STUDENT_MCP_MODE = "proxy"
python scripts/run_student_mcp_http_server.py --host 0.0.0.0 --port 8765 --transport streamable-http
```

See also: [CURSOR_CHAT_MCP_GUIDE.md](../docs/CURSOR_CHAT_MCP_GUIDE.md), [REMOTE_MCP_SERVER_GUIDE.md](../docs/REMOTE_MCP_SERVER_GUIDE.md).
