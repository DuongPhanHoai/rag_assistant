"""Run both LLM-step evaluators in sequence."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = Path(__file__).resolve().parent


def run(script_name: str) -> int:
    script_path = TEST_DIR / script_name
    print(f"\n=== {script_name} ===\n")
    completed = subprocess.run([sys.executable, str(script_path)], cwd=ROOT, check=False)
    return completed.returncode


def main() -> int:
    os.chdir(ROOT)
    plan_code = run("run_plan_eval.py")
    answer_code = run("run_answer_eval.py")

    print("\n=== Summary ===")
    print(f"plan eval exit code: {plan_code}")
    print(f"answer eval exit code: {answer_code}")

    if plan_code != 0 or answer_code != 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
