import argparse

from student_rag.mcp.server import mcp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Student Management MCP over HTTP/SSE.")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind. Use 0.0.0.0 for remote access.")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on.")
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "sse"],
        default="streamable-http",
        help="Remote MCP transport to use.",
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
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.settings.streamable_http_path = args.mcp_path
    mcp.settings.sse_path = args.sse_path
    mcp.settings.message_path = args.message_path

    if args.unsafe_disable_dns_rebinding_protection:
        mcp.settings.transport_security = None

    if args.transport == "streamable-http":
        print(f"Starting Student Management MCP server at http://{args.host}:{args.port}{args.mcp_path}")
    else:
        print(f"Starting Student Management MCP SSE server at http://{args.host}:{args.port}{args.sse_path}")

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
