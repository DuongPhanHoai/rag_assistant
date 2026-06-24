import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from student_rag.paths import ROOT_DIR, VECTOR_DB_DIR  # noqa: E402
from student_rag.retrieval import build_student_vectorstore  # noqa: E402


def main() -> None:
    vectorstore = build_student_vectorstore()
    print(
        "Built student vector store:"
        f" {os.path.relpath(VECTOR_DB_DIR, ROOT_DIR)}"
        f" ({vectorstore._collection.count()} chunks)"
    )


if __name__ == "__main__":
    main()
