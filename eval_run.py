# eval_run.py
import os
import sys
import json
from datetime import datetime

# Ensure current directory is on sys.path so we can import rag_assistant
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from rag_assistant import answer_question  # noqa: E402

EVAL_QUESTIONS_PATH = os.path.join("eval", "questions.json")
EVAL_RESULTS_PATH = os.path.join("eval", "results.jsonl")


def run_eval():
    with open(EVAL_QUESTIONS_PATH, "r", encoding="utf-8") as f:
        questions = json.load(f)

    run_id = datetime.utcnow().isoformat()

    os.makedirs(os.path.dirname(EVAL_RESULTS_PATH), exist_ok=True)

    with open(EVAL_RESULTS_PATH, "a", encoding="utf-8") as f_out:
        for item in questions:
            qid = item.get("id")
            question = item["question"]

            print(f"Running: {qid} - {question}")
            res = answer_question(question)

            record = {
                "run_id": run_id,
                "id": qid,
                "question": question,
                "answer": res["answer"],
                "sources": res["sources"],
            }
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\nEval run completed. Results saved to {EVAL_RESULTS_PATH}")


if __name__ == "__main__":
    run_eval()