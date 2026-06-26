from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from student_rag.paths import DATA_DIR


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    category: str
    metric: str
    operator: str
    threshold_value: float
    term: str
    active: int
    reason_label: str = ""


METRIC_SQL = {
    "avg_score": "g.avg_score",
    "attendance_pct": "a.attendance_pct",
    "balance_due": "f.balance_due",
}


def load_policy_rules(data_dir: Path | None = None) -> list[PolicyRule]:
    data_dir = data_dir or DATA_DIR
    csv_path = data_dir / "policy_rules.csv"
    rules: list[PolicyRule] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if not str(row.get("active", "1")).strip() in {"1", "true", "yes"}:
                continue
            rules.append(
                PolicyRule(
                    rule_id=row["rule_id"],
                    category=row["category"],
                    metric=row["metric"],
                    operator=row["operator"],
                    threshold_value=float(row["threshold_value"]),
                    term=row["term"],
                    active=int(row["active"]),
                    reason_label=str(row.get("reason_label") or "").strip(),
                )
            )
    return rules


def _rule_condition(rule: PolicyRule) -> str:
    metric_expr = METRIC_SQL.get(rule.metric)
    if not metric_expr:
        raise ValueError(f"Unsupported policy metric for SQL view: {rule.metric}")
    value = (
        int(rule.threshold_value)
        if rule.threshold_value == int(rule.threshold_value)
        else rule.threshold_value
    )
    return f"{metric_expr} {rule.operator} {value}"


def _join_conditions(rules: list[PolicyRule], joiner: str) -> str:
    conditions = [_rule_condition(rule) for rule in rules]
    if not conditions:
        return "0"
    if len(conditions) == 1:
        return conditions[0]
    return f"({joiner.join(conditions)})"


def grade_score_threshold(rules: list[PolicyRule]) -> float:
    for rule in rules:
        if rule.category == "risk_high" and rule.metric == "avg_score" and rule.operator == "<":
            return rule.threshold_value
    return 70.0


def build_student_risk_summary_view(rules: list[PolicyRule] | None = None) -> str:
    rules = rules or load_policy_rules()
    high_rules = [rule for rule in rules if rule.category == "risk_high"]
    medium_rules = [rule for rule in rules if rule.category == "risk_medium"]
    scholarship_rules = [rule for rule in rules if rule.category == "scholarship"]
    low_score_threshold = grade_score_threshold(high_rules)

    high_case = _join_conditions(high_rules, " OR ")
    medium_case = _join_conditions(medium_rules, " OR ")
    scholarship_case = _join_conditions(scholarship_rules, " AND ")

    reason_parts: list[str] = []
    for rule in high_rules:
        if not rule.reason_label:
            continue
        reason_parts.append(
            f"CASE WHEN {_rule_condition(rule)} THEN '{rule.reason_label}; ' ELSE '' END"
        )
    risk_reasons_expr = "TRIM(" + " ||\n        ".join(reason_parts) + ")" if reason_parts else "''"

    return f"""
CREATE VIEW student_risk_summary AS
WITH grade AS (
    SELECT
        student_id,
        term,
        ROUND(AVG(weighted_score), 2) AS avg_score,
        SUM(CASE WHEN weighted_score < {low_score_threshold} THEN 1 ELSE 0 END) AS low_score_courses
    FROM assessment_scores
    GROUP BY student_id, term
),
att AS (
    SELECT
        student_id,
        term,
        ROUND(100.0 * SUM(sessions_attended) / SUM(sessions_held), 2) AS attendance_pct
    FROM attendance_summary
    GROUP BY student_id, term
),
fees_due AS (
    SELECT
        student_id,
        term,
        balance_due,
        status
    FROM fee_summary
)
SELECT
    s.student_id,
    s.first_name || ' ' || s.last_name AS student_name,
    s.program,
    s.year_level,
    s.advisor,
    g.term,
    g.avg_score,
    a.attendance_pct,
    f.balance_due,
    f.status AS fee_status,
    g.low_score_courses,
    CASE
        WHEN {high_case} THEN 'high'
        WHEN {medium_case} THEN 'medium'
        ELSE 'low'
    END AS risk_level,
    {risk_reasons_expr} AS risk_reasons,
    CASE
        WHEN {scholarship_case} THEN 1
        ELSE 0
    END AS scholarship_candidate
FROM students s
JOIN grade g ON g.student_id = s.student_id
JOIN att a ON a.student_id = s.student_id AND a.term = g.term
JOIN fees_due f ON f.student_id = s.student_id AND f.term = g.term;
"""
