"""Generate frozen evidence fixtures used by answer-step LLM eval."""
from __future__ import annotations

import json
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from student_rag.agents.deterministic import get_graph_evidence  # noqa: E402
from student_rag.artifacts import generate_table_or_chart_spec  # noqa: E402
from student_rag.data.db import run_sql  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def write_json(name: str, payload: object) -> None:
    path = FIXTURES_DIR / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    risk_sql = run_sql(
        """
        SELECT student_name, program, advisor, avg_score, attendance_pct, balance_due,
               risk_level, risk_reasons, scholarship_candidate
        FROM student_risk_summary
        WHERE risk_level IN ('high', 'medium')
        ORDER BY
            CASE risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            avg_score ASC
        """
    )
    write_json("risk_summary_sql.json", risk_sql)

    attendance_sql = run_sql(
        """
        SELECT t.student_name, t.month, t.attendance_pct
        FROM attendance_trend t
        JOIN student_risk_summary r ON r.student_id = t.student_id AND r.term = t.term
        WHERE r.risk_level IN ('high', 'medium')
        ORDER BY t.student_name, t.month
        """
    )
    write_json("attendance_trend_sql.json", attendance_sql)

    noah_graph = get_graph_evidence(
        "What risk factors are linked to Noah Patel, and which policy and intervention path applies to irregular attendance?",
        "policies interventions risk factors irregular attendance Noah Patel",
    )
    write_json("noah_graph_context.json", noah_graph)

    carlos_graph = get_graph_evidence(
        "What intervention paths does the knowledge graph recommend for Carlos Reyes?",
        "Carlos Reyes intervention paths policies",
    )
    write_json("carlos_graph_context.json", carlos_graph)

    chart_artifact = generate_table_or_chart_spec(
        question="Create a chart of attendance trend by month for at-risk students.",
        sql_result=attendance_sql,
        needs_chart=True,
    )
    write_json("attendance_chart_artifact.json", chart_artifact)

    high_balance_sql = run_sql(
        """
        SELECT student_name, balance_due, risk_level
        FROM student_risk_summary
        WHERE risk_level = 'high'
        ORDER BY balance_due DESC
        """
    )
    write_json("high_risk_balances_sql.json", high_balance_sql)

    attendance_policy_graph = get_graph_evidence(
        "What attendance percentage requires advisor follow-up?",
        "attendance policy advisor follow-up 75 percent",
    )
    write_json("attendance_policy_graph.json", attendance_policy_graph)


if __name__ == "__main__":
    main()
