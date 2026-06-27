from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from student_rag.logging_config import configure_logging
from student_rag.mcp.modes import register_mcp_tools
from student_rag.paths import STUDENT_MCP_MODE


mcp = FastMCP("student-management-rag")
_ACTIVE_MODE: str | None = None


def init_mcp(mode: str | None = None) -> str:
    """Register tools once for the requested mode."""
    global _ACTIVE_MODE
    if _ACTIVE_MODE is not None:
        return _ACTIVE_MODE
    _ACTIVE_MODE = register_mcp_tools(mcp, mode)
    return _ACTIVE_MODE


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Simple HTTP health check for remote connectivity testing."""
    mode = _ACTIVE_MODE or STUDENT_MCP_MODE
    return JSONResponse(
        {
            "status": "ok",
            "service": "student-management-rag",
            "mcp_mode": mode,
            "transport": "http",
        }
    )


def _print_mode_banner(mode: str) -> None:
    print(f"Student Management MCP — mode={mode} (STUDENT_MCP_MODE={STUDENT_MCP_MODE})")
    if mode == "proxy":
        print("  Tool: ask_student_agent (forwards to CLI agent pipeline)")
    else:
        print("  Tools: guide_student_query (call first), get_sqlite_schema, run_sql, ...")


def main() -> None:
    configure_logging()
    mode = init_mcp()
    _print_mode_banner(mode)
    mcp.run()


if __name__ == "__main__":
    main()
