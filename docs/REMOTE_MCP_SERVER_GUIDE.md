# Remote MCP Server Guide

This guide explains how to run the Student Management MCP server on one machine and connect to it from Cursor or LM Studio on another machine.

## 1. When To Use Remote MCP

Use remote MCP when:

- The SQLite database and Chroma vector store live on Machine A.
- Cursor or LM Studio runs on Machine B.
- You do not want to copy the project and rebuild assets on every client machine.

Recommended setup:

```text
Machine A: data/tool server
  - D:\rag_assistant
  - student_management.sqlite
  - chroma_student_db/
  - remote MCP server

Machine B: chat client
  - Cursor or LM Studio
  - connects to Machine A over HTTP/SSE MCP
```

## 2. Start The Server On Machine A

From the project root:

```powershell
cd D:\rag_assistant
pip install -r requirements.txt
python scripts/build_student_db.py
python scripts/build_student_vectors.py
```

Start streamable HTTP MCP:

```powershell
python scripts/run_student_mcp_http_server.py --host 0.0.0.0 --port 8765 --transport streamable-http --unsafe-disable-dns-rebinding-protection
```

Endpoint:

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

## 3. Windows Firewall

Allow inbound traffic to port `8765` on Machine A.

For local LAN testing, keep access limited to your trusted network. Do not expose this server directly to the public internet.

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
192.168.1.20
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

## 6. Test From The Client Machine

From Machine B, check the server is reachable:

```powershell
Invoke-WebRequest http://MACHINE_A_IP:8765/mcp
```

For SSE mode:

```powershell
Invoke-WebRequest http://MACHINE_A_IP:8765/sse
```

The response may not look like a normal web page. The important part is that the request reaches the server and does not fail with connection refused or timeout.

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

### Client Cannot Connect

Check:

- Machine A server is running.
- Machine A firewall allows port `8765`.
- Machine B can ping or reach Machine A.
- The config uses the correct transport path: `/mcp` or `/sse`.

### DNS Rebinding Or Host Header Error

For LAN testing, this guide uses:

```powershell
--unsafe-disable-dns-rebinding-protection
```

This disables FastMCP host/origin restrictions. Use it only on trusted networks.

### Tools Are Visible But Slow

The first vector query may load the embedding model and take longer. After that, retrieval should be faster.

### Prefer Local MCP If Possible

If Cursor/LM Studio and the project are on the same machine, prefer the local stdio server:

```powershell
python scripts/run_student_mcp_server.py
```
