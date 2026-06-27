"""Evaluate planning suite. Prefer: python test/run_eval.py --suite planning [--case ID]."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = ROOT / "test"
SRC = ROOT / "src"

for path in (str(TEST_DIR), str(SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from suites.runner import main  # noqa: E402


if __name__ == "__main__":
    os.chdir(ROOT)
    default_argv = ["--suite", "planning"]
    argv = sys.argv[1:] or default_argv
    if "--suite" not in argv:
        argv = ["--suite", "planning", *argv]
    raise SystemExit(main(argv))
