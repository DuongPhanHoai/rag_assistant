import argparse
import os
import socket

from student_rag.logging_config import configure_logging
from student_rag.mcp.server import init_mcp, mcp
from student_rag.paths import STUDENT_MCP_MODE


def _lan_ip_hint() -> str:
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        probe.close()
        return ip
    except OSError:
        return "MACHINE_A_IP"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Student Management MCP over HTTP/SSE (remote).")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind. Use 0.0.0.0 for remote access.")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on.")
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "sse"],
        default="streamable-http",
        help="Remote MCP transport to use.",
    )
    parser.add_argument(
        "--mode",
        choices=["proxy", "tools"],
        default=None,
        help="MCP mode (overrides STUDENT_MCP_MODE env). proxy=ask_student_agent; tools=schema+SQL/graph tools.",
    )
    parser.add_argument("--mcp-path", default="/mcp", help="Path for streamable HTTP transport.")
    parser.add_argument("--sse-path", default="/sse", help="Path for SSE transport.")
    parser.add_argument("--message-path", default="/messages/", help="Message path for SSE transport.")
    parser.add_argument(
        "--unsafe-disable-dns-rebinding-protection",
        action="store_true",
        help="Disable FastMCP DNS rebinding protection for LAN testing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode:
        os.environ["STUDENT_MCP_MODE"] = args.mode

    configure_logging()
    mode = init_mcp(args.mode)

    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.settings.streamable_http_path = args.mcp_path
    mcp.settings.sse_path = args.sse_path
    mcp.settings.message_path = args.message_path

    if args.unsafe_disable_dns_rebinding_protection:
        mcp.settings.transport_security = None

    lan_ip = _lan_ip_hint()
    print(f"Student Management MCP (remote) — mode={mode}")
    if mode == "proxy":
        print("  Remote clients call: ask_student_agent")
    else:
        print("  Remote clients use: get_sqlite_schema, get_neo4j_schema, run_sql, ...")

    if args.transport == "streamable-http":
        print(f"Listening: http://{args.host}:{args.port}{args.mcp_path}")
        print(f"Health check: http://{lan_ip}:{args.port}/health")
        print(f"Client mcp.json url: http://{lan_ip}:{args.port}{args.mcp_path}")
    else:
        print(f"Listening (SSE): http://{args.host}:{args.port}{args.sse_path}")
        print(f"Health check: http://{lan_ip}:{args.port}/health")
        print(f"Client mcp.json url: http://{lan_ip}:{args.port}{args.sse_path}")

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
