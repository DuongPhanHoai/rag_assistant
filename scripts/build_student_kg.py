import argparse
import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from student_rag.kg.extraction import extract_graph_facts  # noqa: E402
from student_rag.kg.neo4j_store import Neo4jUnavailableError, load_graph_facts  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Student Management Neo4j knowledge graph.")
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Run an additional AutoSchemaKG-style LLM extraction pass over policy CSV content.",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Merge into the existing graph instead of clearing it first.",
    )
    args = parser.parse_args()

    facts = extract_graph_facts(use_llm=args.use_llm)
    try:
        summary = load_graph_facts(facts, reset=not args.no_reset)
    except Neo4jUnavailableError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        f"Loaded {summary['loaded_facts']} graph facts into Neo4j "
        f"(reset={summary['reset']})."
    )
    print(f"Policy CSV source dir: {os.path.relpath(ROOT_DIR / 'data' / 'student_management', ROOT_DIR)}")


if __name__ == "__main__":
    main()
