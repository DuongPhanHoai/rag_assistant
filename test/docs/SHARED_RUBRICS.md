# Shared Rubrics & Case Schema

> Reference for all suites. Linked from [TESTCASES.md](../TESTCASES.md).

## Risk level ground truth

| Level | Students | Thresholds (`policy_rules.csv`) |
|-------|----------|----------------------------------|
| High | Owen Smith, Carlos Reyes, Lina Garcia | `avg_score < 70`, `attendance_pct < 75`, `balance_due > 500` |
| Medium | Noah Patel, Minh Nguyen | `avg_score < 80`, `attendance_pct < 85`, `balance_due > 0` |
| Low | Maya Tran, Aisha Khan, Emma Brown | None of the above |

`risk_reasons` in SQL focuses on **high-risk** triggers and may be **empty for medium-risk** students. Valid answers must still explain medium risk from metrics.

## Policy ground truth (selected)

| Policy | Key facts |
|--------|-----------|
| Academic Risk Policy | avg_score below 70, attendance below 75% |
| Attendance Intervention Policy | follow-up below 75%; expected sessions 80% |
| Scholarship Support Policy | avg_score ≥ 85, attendance ≥ 85%, no overdue balance |
| Financial Hold Policy | overdue balance above 500 |

Source: `data/student_management/policies.csv`, `policy_rules.csv`.

## Forbidden answer phrases (risk cases)

- `no explicit triggers`
- `no reason`
- `no documented risk factors`

## Graph path ground truth (selected)

| Student | Risk factor | Policy | Intervention |
|---------|-------------|--------|--------------|
| Noah Patel | Irregular Attendance | Attendance Intervention Policy | Weekly Lab Attendance |
| Carlos Reyes | Balance Due Greater Than 500 | Financial Hold Policy | Financial Aid Review |
| Carlos Reyes | Irregular Attendance | Attendance Intervention Policy | Weekly Lab Attendance |

## Test layers

| Layer | Function(s) | When to use |
|-------|-------------|-------------|
| `plan` | `plan_question()` | Routing only |
| `pipeline` | Through artifact generation | SQL/graph/chart without final answer LLM |
| `answer` | `answer_from_evidence()` + fixtures | Answer quality in isolation |
| `e2e` | `answer_student_question()` | Full workflow |

## Case JSON shape (planned)

Each suite will use `cases.json` with entries like:

```json
{
  "id": "example_id",
  "layer": "plan",
  "question": "...",
  "notes": "...",
  "expected": {
    "needs_sql": true,
    "needs_graph": false,
    "needs_chart": false,
    "artifact_type": "table"
  },
  "sql_must_contain": ["student_risk_summary"],
  "sql_must_execute": true,
  "must_include": ["Owen Smith"],
  "must_not_include": ["no reason"],
  "any_of": ["structured", "sqlite"],
  "expected_sources": ["policies"],
  "acceptable_alternates": {
    "needs_sql": true,
    "notes": "SQL on policies table acceptable instead of graph-only"
  },
  "fixtures": {
    "plan": {},
    "sql_result": "risk_summary_sql.json",
    "graph_context": null,
    "artifact": {}
  }
}
```

### Graph suite fields ([graph.md](graph.md))

```json
{
  "expected_paths_exact": 2,
  "expected_path_rows": [
    { "student_name": "Carlos Reyes", "risk_factor": "...", "policy": "...", "intervention": "..." }
  ],
  "expected_risk_rows_exact": 0,
  "sources_must_contain": ["policies", "student_risk_factors"],
  "sources_any_of": [],
  "sources_may_contain": []
}
```

- **`sources_must_contain`** — all required (subset check).
- **`sources_any_of`** — at least one required; empty array = unused.
- **`sources_may_contain`** — optional extras; not used alone.
- **`expected_path_rows`** — required set of path tuples; no extras for that student.

## Testing technique legend

| Technique | Abbrev | Meaning in this project |
|-----------|--------|-------------------------|
| Decision table | DT | Combinations of conditions → expected flags/outputs |
| Equivalence partition | EP | One case per question-type class |
| Boundary / range | BR | Threshold edges (70, 75, 80, 85, 500) |
| Exceptional / edge | EX | Ambiguous wording, empty input, off-topic |
| Error | ER | LM down, bad JSON, mutating SQL, missing schema |
| State change | ST | Mode switches, replan after empty SQL — mostly `integration/` |

Each suite document marks which techniques apply and which cases cover them.

## Fixtures index

| File | Contents |
|------|----------|
| `fixtures/risk_summary_sql.json` | 5 at-risk students |
| `fixtures/high_risk_balances_sql.json` | High-risk students by balance |
| `fixtures/attendance_trend_sql.json` | Monthly attendance for at-risk students |
| `fixtures/attendance_chart_artifact.json` | Vega-Lite line chart spec |
| `fixtures/noah_graph_context.json` | Noah Patel risk + policy path |
| `fixtures/carlos_graph_context.json` | Carlos Reyes two intervention paths |
| `fixtures/attendance_policy_graph.json` | Attendance policy graph matches |

Regenerate: `python test/scripts/build_fixtures.py`
