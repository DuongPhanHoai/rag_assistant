# Remote MCP Server Guide

This guide explains how to run the Student Management MCP server on one machine and connect to it from Cursor or LM Studio on another machine.

**MCP modes:** The remote server supports both `proxy` and `tools` modes. See [MCP_MODES.md](MCP_MODES.md). Set mode when starting the server (`--mode proxy` or `--mode tools`); clients use the same URL either way.

## 1. When To Use Remote MCP

Use remote MCP when:

- The SQLite database lives on Machine A.
- Cursor or LM Studio runs on Machine B.
- You do not want to copy the project and rebuild assets on every client machine.

Recommended setup:

```text
Machine A: MCP server + data
  - D:\rag_assistant
  - student_management.sqlite
  - Neo4j (for graph tools / proxy agent)
  - LM Studio (required for proxy mode when LLM_ONLINE_MODE=true)
  - remote MCP server (HTTP/SSE)

Machine B: chat client
  - Cursor or LM Studio
  - connects to Machine A over HTTP/SSE MCP
```

MCP reads SQLite and Neo4j on Machine A only.

## 2. Start The Server On Machine A

From the project root:

```powershell
cd D:\rag_assistant
pip install -r requirements.txt
python scripts/build_student_db.py
python scripts/build_student_kg.py
```

### Mode 2 — tools (default): schema + SQL/graph tools

Host model on Machine B plans queries; Machine A runs tools:

```powershell
python scripts/run_student_mcp_http_server.py --host 0.0.0.0 --port 8765 --mode tools --transport streamable-http --unsafe-disable-dns-rebinding-protection
```

### Mode 1 — proxy: forward to CLI agent on Machine A

Machine A runs the full agent pipeline (needs LM Studio when `LLM_ONLINE_MODE=true`):

```powershell
$env:LLM_ONLINE_MODE = "true"
python scripts/run_student_mcp_http_server.py --host 0.0.0.0 --port 8765 --mode proxy --transport streamable-http --unsafe-disable-dns-rebinding-protection
```

### Legacy (same as --mode tools)

Start streamable HTTP MCP:

```powershell
python scripts/run_student_mcp_http_server.py --host 0.0.0.0 --port 8765 --transport streamable-http --unsafe-disable-dns-rebinding-protection
```

Wait until you see:

```text
Student Management MCP (remote) — mode=tools
Listening: http://0.0.0.0:8765/mcp
Health check: http://192.168.x.x:8765/health
Client mcp.json url: http://192.168.x.x:8765/mcp
```

Confirm mode via health check — response includes `"mcp_mode": "tools"` or `"proxy"`.

The first startup can take 20–40 seconds while Python loads dependencies.

Endpoint for LM Studio:

```text
http://MACHINE_A_IP:8765/mcp
```

Alternative SSE transport:

```powershell
python scripts/run_student_mcp_http_server.py --host 0.0.0.0 --port 8765 --transport sse --unsafe-disable-dns-rebinding-protection
```

SSE endpoint:

```text
http://MACHINE_A_IP:8765/sse
```

## 3. Windows Firewall On Machine A

The server can work locally but still be blocked from other machines. Open port `8765` on Machine A.

PowerShell (run as Administrator on Machine A):

```powershell
New-NetFirewallRule -DisplayName "Student MCP 8765" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
```

Also confirm Machine A's LAN IP:

```powershell
ipconfig
```

Use the `IPv4 Address` from your active Wi‑Fi or Ethernet adapter, for example `192.168.1.168`. Do not use `127.0.0.1` or `localhost` in LM Studio on Machine B.

## 4. Cursor Remote MCP Config

If Cursor supports remote MCP by URL, use streamable HTTP:

```json
{
  "mcpServers": {
    "student-management-rag": {
      "url": "http://MACHINE_A_IP:8765/mcp"
    }
  }
}
```

If your Cursor version expects SSE:

```json
{
  "mcpServers": {
    "student-management-rag": {
      "url": "http://MACHINE_A_IP:8765/sse"
    }
  }
}
```

Replace `MACHINE_A_IP` with the actual LAN IP address, for example:

```text
192.168.1.168
```

## 5. LM Studio Remote MCP Config

In LM Studio, open `mcp.json` and add:

```json
{
  "mcpServers": {
    "student-management-rag": {
      "url": "http://MACHINE_A_IP:8765/mcp"
    }
  }
}
```

If streamable HTTP does not work in your LM Studio version, run the server with `--transport sse` and configure:

```json
{
  "mcpServers": {
    "student-management-rag": {
      "url": "http://MACHINE_A_IP:8765/sse"
    }
  }
}
```

Enable MCP from `mcp.json` in LM Studio server settings if that option exists in your version.

## 6. Test Connectivity

### Important: `/mcp` is not a normal web page

Opening `http://MACHINE_A_IP:8765/mcp` in a browser often shows **406 Not Acceptable**. That usually means the server is running. The `/mcp` endpoint expects MCP protocol headers, not a browser GET.

Use the health endpoint instead:

```powershell
Invoke-WebRequest http://MACHINE_A_IP:8765/health
```

Expected response:

```json
{"status":"ok","service":"student-management-rag"}
```

### Test from Machine A (same machine)

```powershell
Invoke-WebRequest http://127.0.0.1:8765/health
Invoke-WebRequest http://192.168.x.x:8765/health
```

Both should return `status: ok`.

### Test from Machine B (LM Studio machine)

```powershell
Invoke-WebRequest http://MACHINE_A_IP:8765/health
```

| Result | Meaning |
|--------|---------|
| `{"status":"ok",...}` | Network path works; configure LM Studio with the matching `/mcp` or `/sse` URL |
| `Connection refused` | Server not running, wrong port, or firewall blocking |
| `Timed out` | Wrong IP, different subnet, or firewall blocking |
| `406` on `/mcp` only | Server is up; use `/health` for browser tests |

### Verify the server is listening on Machine A

```powershell
netstat -ano | findstr :8765
```

You should see `LISTENING` on `0.0.0.0:8765`.

## 7. Chat Prompt

In Cursor or LM Studio Chat:

```text
Using the student-management-rag tools, which students are at risk this term and why?
```

For scholarship:

```text
Using the student-management-rag tools, who qualifies for scholarship support based on score, attendance, and fee status?
```

## 8. Security Notes

This sample has no authentication.

Do:

- Run only on a trusted LAN.
- Keep firewall access narrow.
- Avoid exposing the port to the public internet.
- Treat retrieved student data as sensitive.

Do not:

- Bind to `0.0.0.0` on an untrusted network.
- Put this behind a public IP without authentication, TLS, and access controls.

## 9. Troubleshooting

### Browser shows 406 on `/mcp`

This is normal. The MCP endpoint is not meant for browsers. Test `/health` instead.

### Client cannot connect (refused or timeout)

Check:

- Machine A server is running and shows `Uvicorn running on http://0.0.0.0:8765`.
- Machine A firewall allows inbound TCP `8765`.
- Machine B uses Machine A's LAN IP (`192.168.x.x`), not `localhost`.
- The IP is not mistyped (for example `182.168.x.x` instead of `192.168.x.x`).
- Server transport matches client URL: `streamable-http` → `/mcp`, `sse` → `/sse`.
- Both machines are on the same network.

### DNS rebinding or host header error

For LAN testing, start the server with:

```powershell
--unsafe-disable-dns-rebinding-protection
```

Use this only on trusted networks.

### LM Studio shows tools but they fail

Try SSE transport on the server and switch the client URL to `/sse`.

### Tools are visible but slow

The first MCP SQL query may load Python dependencies and take longer on cold start. After that, SQLite queries should be fast.

### Prefer local MCP if possible

If Cursor/LM Studio and the project are on the same machine, prefer the local stdio server:

```powershell
python scripts/run_student_mcp_server.py
```
