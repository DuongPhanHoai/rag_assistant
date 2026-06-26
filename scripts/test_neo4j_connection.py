import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from student_rag.kg.neo4j_store import run_read_only_cypher  # noqa: E402
from student_rag.paths import NEO4J_DATABASE, NEO4J_URI, NEO4J_USER  # noqa: E402


def main() -> None:
    print(f"Testing Neo4j at {NEO4J_URI} as {NEO4J_USER} (database={NEO4J_DATABASE})")
    result = run_read_only_cypher("MATCH (n) RETURN labels(n) AS labels, count(*) AS count")
    print("Connection OK.")
    print(result["rows"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"Neo4j connection failed: {exc}") from exc
