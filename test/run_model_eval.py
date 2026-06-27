"""Run all eval cases for the current LMSTUDIO_MODEL and append CSV history."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = Path(__file__).resolve().parent
SRC = ROOT / "src"

for path in (str(TEST_DIR), str(SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from suites.runner import run_model_eval  # noqa: E402

if __name__ == "__main__":
    os.chdir(ROOT)
    raise SystemExit(run_model_eval())
