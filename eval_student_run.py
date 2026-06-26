# eval_student_run.py
import json
import os
import sys
from datetime import UTC, datetime


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(CURRENT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.append(SRC_DIR)

from student_rag.agents.deterministic import answer_student_question  # noqa: E402


EVAL_QUESTIONS_PATH = os.path.join("eval", "student_questions.json")
EVAL_RESULTS_PATH = os.path.join("eval", "student_results.jsonl")


def run_eval():
    with open(EVAL_QUESTIONS_PATH, "r", encoding="utf-8") as f:
        questions = json.load(f)

    run_id = datetime.now(UTC).isoformat()
    os.makedirs(os.path.dirname(EVAL_RESULTS_PATH), exist_ok=True)

    with open(EVAL_RESULTS_PATH, "a", encoding="utf-8") as f_out:
        for item in questions:
            qid = item.get("id")
            question = item["question"]

            print(f"Running: {qid} - {question}")
            res = answer_student_question(question)

            record = {
                "run_id": run_id,
                "id": qid,
                "question": question,
                "answer": res["answer"],
                "plan": res["plan"],
                "sql": (res["sql_result"] or {}).get("sql"),
                "artifact_type": res["artifact"]["type"],
                "graph_match_count": (res.get("graph_context") or {}).get("row_count", 0),
                "sources": res["sources"],
            }
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\nStudent eval run completed. Results saved to {EVAL_RESULTS_PATH}")


if __name__ == "__main__":
    run_eval()
