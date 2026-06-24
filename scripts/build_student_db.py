import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from student_rag.db import build_database  # noqa: E402
from student_rag.paths import ROOT_DIR  # noqa: E402


def main() -> None:
    path = build_database()
    print(f"Built SQLite database: {os.path.relpath(path, ROOT_DIR)}")


if __name__ == "__main__":
    main()
