import csv
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from student_rag.data.policy_loader import build_student_risk_summary_view, load_policy_rules
from student_rag.paths import DATA_DIR, DB_PATH


logger = logging.getLogger(__name__)


MAX_SQL_ROWS = 50
BLOCKED_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|vacuum|pragma)\b",
    re.IGNORECASE,
)

TABLE_FILES = {
    "students": "students.csv",
    "courses": "courses.csv",
    "enrollments": "enrollments.csv",
    "attendance": "attendance.csv",
    "assessments": "assessments.csv",
    "fees": "fees.csv",
}

POLICY_TABLE_FILES = {
    "policy_rules": "policy_rules.csv",
    "policies": "policies.csv",
    "interventions": "interventions.csv",
    "risk_policy_links": "risk_policy_links.csv",
    "policy_intervention_links": "policy_intervention_links.csv",
    "advising_notes": "advising_notes.csv",
    "student_risk_factors": "student_risk_factors.csv",
    "student_interventions": "student_interventions.csv",
    "course_policy_links": "course_policy_links.csv",
}


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS attendance_trend;
DROP VIEW IF EXISTS course_performance_summary;
DROP VIEW IF EXISTS student_risk_summary;
DROP VIEW IF EXISTS fee_summary;
DROP VIEW IF EXISTS attendance_summary;
DROP VIEW IF EXISTS assessment_scores;

DROP TABLE IF EXISTS student_interventions;
DROP TABLE IF EXISTS student_risk_factors;
DROP TABLE IF EXISTS advising_notes;
DROP TABLE IF EXISTS course_policy_links;
DROP TABLE IF EXISTS policy_intervention_links;
DROP TABLE IF EXISTS risk_policy_links;
DROP TABLE IF EXISTS interventions;
DROP TABLE IF EXISTS policies;
DROP TABLE IF EXISTS policy_rules;
DROP TABLE IF EXISTS fees;
DROP TABLE IF EXISTS assessments;
DROP TABLE IF EXISTS attendance;
DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS students;

CREATE TABLE students (
    student_id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    program TEXT NOT NULL,
    year_level INTEGER NOT NULL,
    advisor TEXT NOT NULL,
    email TEXT NOT NULL
);

CREATE TABLE courses (
    course_id TEXT PRIMARY KEY,
    course_name TEXT NOT NULL,
    department TEXT NOT NULL,
    credits INTEGER NOT NULL,
    instructor TEXT NOT NULL,
    description TEXT
);

CREATE TABLE enrollments (
    enrollment_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(student_id),
    course_id TEXT NOT NULL REFERENCES courses(course_id),
    term TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE attendance (
    attendance_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(student_id),
    course_id TEXT NOT NULL REFERENCES courses(course_id),
    term TEXT NOT NULL,
    month TEXT NOT NULL,
    sessions_held INTEGER NOT NULL,
    sessions_attended INTEGER NOT NULL
);

CREATE TABLE assessments (
    assessment_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(student_id),
    course_id TEXT NOT NULL REFERENCES courses(course_id),
    term TEXT NOT NULL,
    assessment_name TEXT NOT NULL,
    score REAL NOT NULL,
    max_score REAL NOT NULL,
    weight REAL NOT NULL
);

CREATE TABLE fees (
    fee_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(student_id),
    term TEXT NOT NULL,
    total_due REAL NOT NULL,
    amount_paid REAL NOT NULL,
    due_date TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE policy_rules (
    rule_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    metric TEXT NOT NULL,
    operator TEXT NOT NULL,
    threshold_value REAL NOT NULL,
    term TEXT NOT NULL,
    active INTEGER NOT NULL,
    reason_label TEXT
);

CREATE TABLE policies (
    policy_id TEXT PRIMARY KEY,
    policy_name TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    source_section TEXT
);

CREATE TABLE interventions (
    intervention_id TEXT PRIMARY KEY,
    intervention_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL
);

CREATE TABLE risk_policy_links (
    risk_factor TEXT NOT NULL,
    policy_id TEXT NOT NULL REFERENCES policies(policy_id),
    evidence_text TEXT NOT NULL,
    source_data TEXT NOT NULL,
    PRIMARY KEY (risk_factor, policy_id)
);

CREATE TABLE policy_intervention_links (
    policy_id TEXT NOT NULL REFERENCES policies(policy_id),
    intervention_id TEXT NOT NULL REFERENCES interventions(intervention_id),
    evidence_text TEXT NOT NULL,
    source_data TEXT NOT NULL,
    PRIMARY KEY (policy_id, intervention_id)
);

CREATE TABLE advising_notes (
    note_id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES students(student_id),
    term TEXT NOT NULL,
    note_text TEXT NOT NULL,
    recommended_intervention_id TEXT REFERENCES interventions(intervention_id)
);

CREATE TABLE student_risk_factors (
    student_id TEXT NOT NULL REFERENCES students(student_id),
    term TEXT NOT NULL,
    risk_factor TEXT NOT NULL,
    evidence_text TEXT NOT NULL,
    source_data TEXT NOT NULL,
    PRIMARY KEY (student_id, term, risk_factor)
);

CREATE TABLE student_interventions (
    student_id TEXT NOT NULL REFERENCES students(student_id),
    term TEXT NOT NULL,
    intervention_id TEXT NOT NULL REFERENCES interventions(intervention_id),
    evidence_text TEXT NOT NULL,
    source_data TEXT NOT NULL,
    PRIMARY KEY (student_id, term, intervention_id)
);

CREATE TABLE course_policy_links (
    course_id TEXT NOT NULL REFERENCES courses(course_id),
    policy_id TEXT NOT NULL REFERENCES policies(policy_id),
    evidence_text TEXT NOT NULL,
    source_data TEXT NOT NULL,
    PRIMARY KEY (course_id, policy_id)
);
"""


VIEW_SQL_PREFIX = """
CREATE VIEW assessment_scores AS
SELECT
    a.student_id,
    s.first_name || ' ' || s.last_name AS student_name,
    a.course_id,
    c.course_name,
    a.term,
    ROUND(SUM((a.score / a.max_score) * 100.0 * a.weight) / SUM(a.weight), 2) AS weighted_score
FROM assessments a
JOIN students s ON s.student_id = a.student_id
JOIN courses c ON c.course_id = a.course_id
GROUP BY a.student_id, a.course_id, a.term;

CREATE VIEW attendance_summary AS
SELECT
    a.student_id,
    s.first_name || ' ' || s.last_name AS student_name,
    a.course_id,
    c.course_name,
    a.term,
    SUM(a.sessions_held) AS sessions_held,
    SUM(a.sessions_attended) AS sessions_attended,
    ROUND(100.0 * SUM(a.sessions_attended) / SUM(a.sessions_held), 2) AS attendance_pct
FROM attendance a
JOIN students s ON s.student_id = a.student_id
JOIN courses c ON c.course_id = a.course_id
GROUP BY a.student_id, a.course_id, a.term;

CREATE VIEW fee_summary AS
SELECT
    f.student_id,
    s.first_name || ' ' || s.last_name AS student_name,
    f.term,
    f.total_due,
    f.amount_paid,
    ROUND(f.total_due - f.amount_paid, 2) AS balance_due,
    f.status
FROM fees f
JOIN students s ON s.student_id = f.student_id;
"""


VIEW_SQL_SUFFIX = """
CREATE VIEW course_performance_summary AS
SELECT
    c.course_id,
    c.course_name,
    c.department,
    e.term,
    COUNT(DISTINCT e.student_id) AS enrolled_students,
    ROUND(AVG(sc.weighted_score), 2) AS avg_score,
    ROUND(AVG(att.attendance_pct), 2) AS avg_attendance_pct
FROM courses c
JOIN enrollments e ON e.course_id = c.course_id
LEFT JOIN assessment_scores sc
    ON sc.course_id = e.course_id
    AND sc.student_id = e.student_id
    AND sc.term = e.term
LEFT JOIN attendance_summary att
    ON att.course_id = e.course_id
    AND att.student_id = e.student_id
    AND att.term = e.term
GROUP BY c.course_id, c.course_name, c.department, e.term;

CREATE VIEW attendance_trend AS
SELECT
    a.student_id,
    s.first_name || ' ' || s.last_name AS student_name,
    a.term,
    a.month,
    SUM(a.sessions_held) AS sessions_held,
    SUM(a.sessions_attended) AS sessions_attended,
    ROUND(100.0 * SUM(a.sessions_attended) / SUM(a.sessions_held), 2) AS attendance_pct
FROM attendance a
JOIN students s ON s.student_id = a.student_id
GROUP BY a.student_id, a.term, a.month;
"""


def load_csv_table(conn: sqlite3.Connection, table_name: str, csv_name: str) -> None:
    csv_path = DATA_DIR / csv_name
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        placeholders = ", ".join(["?"] * len(columns))
        column_list = ", ".join(columns)
        rows = [
            tuple(row[column] if row[column] != "" else None for column in columns)
            for row in reader
        ]

    conn.executemany(
        f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})",
        rows,
    )


def build_view_sql() -> str:
    rules = load_policy_rules()
    return VIEW_SQL_PREFIX + build_student_risk_summary_view(rules) + VIEW_SQL_SUFFIX


def build_database(db_path: Path = DB_PATH) -> Path:
    if not DATA_DIR.is_dir():
        raise FileNotFoundError(f"Student data directory not found: {DATA_DIR}")

    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        for table_name, csv_name in TABLE_FILES.items():
            load_csv_table(conn, table_name, csv_name)
        for table_name, csv_name in POLICY_TABLE_FILES.items():
            load_csv_table(conn, table_name, csv_name)
        conn.executescript(build_view_sql())
        conn.commit()
    finally:
        conn.close()

    return db_path


def ensure_database() -> None:
    if not DB_PATH.exists():
        build_database()


def get_schema_summary() -> str:
    ensure_database()
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT name, type
            FROM sqlite_master
            WHERE type IN ('table', 'view')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()

        lines = []
        for name, object_type in rows:
            columns = conn.execute(f"PRAGMA table_info({name})").fetchall()
            column_names = ", ".join(
                f"{column[1]} {column[2]}".strip()
                for column in columns
            )
            lines.append(f"- {object_type} {name}: {column_names}")
        lines.extend(
            [
                "",
                "Important value hints:",
                "- student_risk_summary.risk_level uses text values: 'high', 'medium', 'low'.",
                "- student_risk_summary thresholds come from policy_rules loaded from policy_rules.csv.",
                "- student_risk_summary.scholarship_candidate uses integer values: 1 means yes, 0 means no.",
                "- student_risk_summary.term uses values such as '2026-Spring'; there is no 'current_term' value.",
                "- fee_summary.status uses text values: 'paid', 'partial', 'overdue'.",
                "- Policy and intervention relationships use policy_id and intervention_id foreign keys in link tables.",
            ]
        )
        summary = "\n".join(lines)
        logger.info("get_schema_summary result:\n%s", summary)
        return summary
    finally:
        conn.close()


def validate_read_only_sql(sql: str) -> str:
    cleaned = sql.strip()
    if not cleaned:
        raise ValueError("SQL is empty")

    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].strip()
    if ";" in cleaned:
        raise ValueError("Only one SQL statement is allowed")
    if BLOCKED_SQL.search(cleaned):
        raise ValueError("Only read-only SELECT/WITH SQL is allowed")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise ValueError("SQL must start with SELECT or WITH")

    return cleaned


def run_sql(sql: str, limit: int = MAX_SQL_ROWS) -> dict[str, Any]:
    ensure_database()
    cleaned = validate_read_only_sql(sql)
    warnings = []
    if re.search(r"scholarship_candidate\s*=\s*['\"]yes['\"]", cleaned, re.IGNORECASE):
        warnings.append("scholarship_candidate is an integer flag. Use scholarship_candidate = 1 for yes.")
    if re.search(r"scholarship_candidate\s*=\s*['\"]no['\"]", cleaned, re.IGNORECASE):
        warnings.append("scholarship_candidate is an integer flag. Use scholarship_candidate = 0 for no.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(cleaned)
        rows = cursor.fetchmany(limit + 1)
        columns = [description[0] for description in cursor.description or []]
        limited = len(rows) > limit
        rows = rows[:limit]
        return {
            "sql": cleaned,
            "columns": columns,
            "rows": [dict(row) for row in rows],
            "row_count": len(rows),
            "limited": limited,
            "warnings": warnings,
        }
    finally:
        conn.close()
