# SQL Query & Table Output — Test Specification

> **Status:** Review only — no `sql/cases.json` or runner yet.  
> **Suite folder (planned):** `test/sql/`  
> **Layer:** `pipeline` (primary), `sql_only` (deterministic, no LLM)  
> **Functions:** `plan_question()` → `run_sql()` → `generate_table_or_chart_spec()`

---

## 0. Scope

This suite tests **structured retrieval quality**:

- Planned or injected **read-only SQL**
- **Execution** via `run_sql()` (validator + SQLite)
- **Tabular artifact** (`artifact.type == "table"`) and row grounding

**Out of scope:**

| Topic | Suite |
|-------|-------|
| Routing flags (`needs_*`) | [planning.md](planning.md) |
| Chart / Vega-Lite | [chart.md](chart.md) |
| Policy prose / graph paths | [kg.md](graph.md), [graph.md](graph.md) |
| Final answer text (LLM step 2) | [integration.md](integration.md) |
| LM Studio connectivity | [integration.md](integration.md) |

---

## 1. Goal

Verify SQL is **safe**, targets the **right schema object**, **executes**, and returns **rows that match ground truth**.

Table markdown is built by `generate_table_or_chart_spec()` — **deterministic**, not LLM output. This suite does **not** score prose or markdown formatting.

---

## 2. Does this suite evaluate the LLM?

**Partially — one LLM touchpoint only.**

```text
                    LLM?    What is scored
                    ─────   ─────────────────────────────────────────
plan_question()     YES*    SQL text (fragments, safety) when layer=pipeline
run_sql()           NO      Execution, warnings, row_count, columns
generate_table…     NO      artifact.type, row data in artifact
answer_from_evidence NO     (out of scope)

* Only when LLM_ONLINE_MODE=true and layer=pipeline
```

| Layer | LLM used? | Purpose |
|-------|-----------|---------|
| **`pipeline`** | **Yes** (step 1) | End-to-end: natural-language prompt → LLM plans SQL → validate execution + rows |
| **`sql_only`** | **No** | Regression: fixed SQL string in case JSON → `run_sql()` + row checks only |

**Recommendation:** Keep both layers:

- **`sql_only`** — stable CI without LM Studio; tests validator, schema, ground truth.
- **`pipeline`** — periodic / manual eval of LLM SQL generation quality.

This suite does **not** call `answer_from_evidence()` (LLM step 2).

---

## 3. How techniques relate to test cases

```text
Testing technique          What it defines                    Becomes in cases.json
──────────────────────────────────────────────────────────────────────────────────
Decision table (DT)    →   Question topic → view/join pattern → sql_must_contain[]
Equivalence partition (EP) → One case per query shape class    → one prompt per partition
Boundary / range (BR)  →   Thresholds & LIMIT edges            → boundary prompts + expected rows
Exceptional (EX)       →   Bad schema, empty results           → edge prompts
Error (ER)             →   Invalid SQL inputs                  → injected SQL (sql_only, no LLM)
State change (ST)      →   Replan / fallback SQL               → NOT primary here → integration
```

**Read order:**

1. [Master traceability table](#4-master-traceability-table)
2. [Decision table](#5-decision-table-dt--pattern-to-cases)
3. [Equivalence partitions](#6-equivalence-partitions-ep)
4. [Case catalog](#7-case-catalog)
5. [Coverage gaps](#10-coverage-gaps)

---

## 4. Master traceability table

| Case ID | Tech | DT pattern | EP partition | Layer | LLM? | Primary assertion |
|---------|:----:|:----------:|:------------:|:-----:|:----:|-------------------|
| `agg_students_per_course` | DT, EP | PAT-AGG | EP-AGG | pipeline / sql_only | pipeline only | GROUP BY; counts match seed |
| `top_by_avg_score` | DT, EP | PAT-SORT | EP-SORT-LIMIT | pipeline / sql_only | pipeline only | LIMIT 3; Maya Tran #1 |
| `risk_summary_table` | DT, EP | PAT-RISK | EP-FILTER-VIEW | pipeline / sql_only | pipeline only | 5 at-risk rows; uses view |
| `scholarship_filter` | DT, EP | PAT-SCHOLAR | EP-SCHOLARSHIP | pipeline / sql_only | pipeline only | `scholarship_candidate = 1` |
| `course_performance` | DT, EP | PAT-COURSE | EP-COURSE | pipeline / sql_only | pipeline only | `course_performance_summary` |
| `enrollment_list_c101` | DT, EP | PAT-JOIN | EP-JOIN | pipeline / sql_only | pipeline only | C101 enrollments |
| `fee_balance_ranking` | DT, EP | PAT-FEE | EP-FEE | pipeline / sql_only | pipeline only | Descending balance |
| `assessment_by_course` | EP | PAT-ASSESS | EP-ASSESSMENT | pipeline / sql_only | pipeline only | `assessment_scores` view |
| `boundary_high_risk_score` | BR | PAT-RISK | — | sql_only | **No** | Rows all have avg_score < 70 |
| `boundary_attendance_75` | BR | PAT-RISK | — | sql_only | **No** | attendance_pct < 75 |
| `boundary_balance_500` | BR | PAT-FEE | — | sql_only | **No** | balance_due > 500 |
| `boundary_scholarship_85` | BR | PAT-SCHOLAR | — | sql_only | **No** | avg_score >= 85 + flag |
| `limit_top_3` | BR | PAT-SORT | — | pipeline | pipeline only | Exactly 3 rows |
| `limit_top_10` | BR | PAT-SORT | — | pipeline | pipeline only | ≤10 rows ordered |
| `nonexistent_column` | EX | — | — | pipeline | pipeline only | SQL error; no fake column |
| `wrong_flag_type` | EX, ER | — | — | sql_only | **No** | Injected `='yes'` → warning |
| `empty_result_valid` | EX | — | — | sql_only | **No** | 0 rows; artifact empty message |
| `multi_statement_sql` | ER | — | — | sql_only | **No** | Validator rejects |
| `mutating_sql` | ER | — | — | sql_only | **No** | Validator rejects DELETE/DROP |

**Legend:** PAT-* = decision-table SQL pattern (§5)

---

## 5. Decision table (DT) — pattern to cases

Maps **question topic** → **expected SQL shape** (not routing flags — that is planning).

| Pattern | IF question topic… | sql_must_contain (min) | Test case(s) |
|---------|-------------------|------------------------|--------------|
| **PAT-RISK** | at risk / risk_level | `student_risk_summary` | `risk_summary_table`, `boundary_*` (risk) |
| **PAT-COURSE** | course / average grade / weak | `course_performance_summary` | `course_performance` |
| **PAT-JOIN** | enrolled in / enrollment | `enrollments` | `enrollment_list_c101` |
| **PAT-SCHOLAR** | scholarship | `scholarship_candidate` | `scholarship_filter`, `boundary_scholarship_85` |
| **PAT-FEE** | fee / balance | `fee_summary` or `balance` | `fee_balance_ranking`, `boundary_balance_500` |
| **PAT-AGG** | count per / number of students per | `group by` | `agg_students_per_course` |
| **PAT-SORT** | top N / ordered by | `order by` | `top_by_avg_score`, `limit_top_*` |
| **PAT-ASSESS** | assessment / scores by course | `assessment_scores` | `assessment_by_course` |

---

## 6. Equivalence partitions (EP)

| EP ID | Query class | Case | LLM in pipeline mode |
|-------|-------------|------|----------------------|
| EP-AGG | Aggregation | `agg_students_per_course` | Must generate GROUP BY |
| EP-SORT-LIMIT | Sort + limit | `top_by_avg_score` | Must generate ORDER BY + LIMIT |
| EP-FILTER-VIEW | View filter | `risk_summary_table` | Must pick risk view |
| EP-SCHOLARSHIP | Integer flag | `scholarship_filter` | Must not use `'yes'` |
| EP-COURSE | Course analytics | `course_performance` | Course performance view |
| EP-FEE | Fee ranking | `fee_balance_ranking` | Balance ordering |
| EP-JOIN | Enrollment join | `enrollment_list_c101` | Join enrollments + students |
| EP-ASSESSMENT | Assessment view | `assessment_by_course` | assessment_scores |

**EP completeness:** 8 partitions → 8 cases (BR/EX/ER cases are additive, not EP replacements).

---

## 7. Case catalog

### 7.1 Core (DT + EP) — `layer: pipeline` or `sql_only`

| ID | Tech | Prompt | sql_must_contain | Row / artifact checks |
|----|------|--------|------------------|------------------------|
| `agg_students_per_course` | DT, EP | Show the number of students per course as a table sorted by most popular course. | `group by` | artifact.type=table; counts match reference query |
| `top_by_avg_score` | DT, EP | List the top 3 students by avg_score with program and advisor. | `order by`, `limit` | 3 rows; first is Maya Tran |
| `risk_summary_table` | DT, EP | Which students are at risk this term? Show as a table. | `student_risk_summary` | 5 rows; 3 high + 2 medium |
| `scholarship_filter` | DT, EP | Who qualifies for scholarship support? | `scholarship_candidate` | All rows have flag = 1 |
| `course_performance` | DT, EP | Show each course with average score and number of students. | `course_performance_summary` | 5 courses |
| `enrollment_list_c101` | DT, EP | List all students enrolled in C101. | `enrollments`, `c101` | ≥1 row |
| `fee_balance_ranking` | DT, EP | Show students ordered by largest balance_due. | `balance` | Descending balance |
| `assessment_by_course` | EP | Show average assessment score by course for 2026-Spring. | `assessment_scores` | Executes with rows |

For **`sql_only`** entries, add field `"sql": "SELECT ..."` (reference SQL) and skip `question` or ignore LLM.

### 7.2 Boundary / range (BR) — prefer `layer: sql_only` (no LLM)

| ID | Tech | Reference condition | Expected row property |
|----|------|---------------------|------------------------|
| `boundary_high_risk_score` | BR | avg_score < 70 | Every row avg_score < 70 |
| `boundary_attendance_75` | BR | attendance_pct < 75 | Every row attendance_pct < 75 |
| `boundary_balance_500` | BR | balance_due > 500 | Every row balance_due > 500 |
| `boundary_scholarship_85` | BR | scholarship rules | avg_score ≥ 85, attendance ≥ 85, balance ≤ 0 |
| `limit_top_3` | BR | LIMIT 3 | row_count = 3 |
| `limit_top_10` | BR | LIMIT 10 | row_count ≤ 10 |

Aligned with `policy_rules.csv` R001–R003, R007–R009.

### 7.3 Exceptional (EX)

| ID | Tech | Layer | Prompt / setup | Expected |
|----|------|-------|----------------|----------|
| `nonexistent_column` | EX | pipeline | Show each student's favorite color. | SQL error from SQLite; no successful fake column |
| `empty_result_valid` | EX | sql_only | SQL: avg_score < 10 | row_count = 0; table artifact "No rows returned." |
| `wrong_flag_type` | EX, ER | sql_only | Injected SQL with `scholarship_candidate = 'yes'` | `warnings` non-empty in sql_result |

### 7.4 Error (ER) — `layer: sql_only` only (deterministic validator)

| ID | Tech | Injected SQL | Expected |
|----|------|--------------|----------|
| `multi_statement_sql` | ER | `SELECT 1; SELECT 2` | `validate_read_only_sql` raises |
| `mutating_sql` | ER | `DELETE FROM students` | Rejected before execute |

No LLM — tests `db.validate_read_only_sql()` directly.

---

## 8. Pass / fail criteria

### All SQL cases

1. SQL passes read-only validator (starts with SELECT/WITH; no mutating keywords; single statement).
2. Execution succeeds **or** case expects a structured error (EX/ER).
3. `sql_must_contain` fragments present (case-insensitive) when `layer=pipeline`.
4. `artifact.type == "table"` when case expects tabular output.

### Pipeline layer (LLM involved)

5. `plan.needs_sql == true` (prerequisite — or assume planning suite passed).
6. Planned SQL meets (1)–(3); row checks vs ground truth.

### sql_only layer (no LLM)

5. Fixed `case["sql"]` meets (1)–(4); row checks vs `expected_rows` or reference query.

### Row matching strategy (proposed)

| Level | Method |
|-------|--------|
| **Strict** | Full row dict equality vs reference query |
| **Pragmatic (v1)** | Key columns + row_count + sorted keys |

---

## 9. Techniques summary — full matrix

| Technique | Applied? | # Cases (planned) | LLM involved? | Notes |
|-----------|:--------:|:-----------------:|:-------------:|-------|
| **Decision table (DT)** | **Yes** | 8 patterns → 8 core | Only in `pipeline` layer | View/join selection |
| **Equivalence partition (EP)** | **Yes** | 8 | Only in `pipeline` | One shape per class |
| **Boundary / range (BR)** | **Yes** | 6 | **No** (sql_only) | Thresholds from policy_rules |
| **Exceptional (EX)** | **Yes** | 3 | Mixed | Missing column needs LLM plan |
| **Error (ER)** | **Yes** | 3 | **No** | Validator + injected bad SQL |
| **State change (ST)** | **No** | 0 | — | `replan_if_needed` → [integration.md](integration.md) |

**Answer:** All techniques **except ST** are applied. ST belongs in integration (replan when first SQL returns 0 rows).

---

## 10. Coverage gaps

| Gap | Technique | Action |
|-----|-----------|--------|
| Replan after empty SQL | ST | [integration.md](integration.md) — `empty_sql_replan` |
| LLM step 2 answer quality | — | Not this suite |
| Exact join path (raw tables vs views) | DT | Open — prefer views in v1 |
| Wildcard SELECT * | EX | Optional case — defer |
| SQL injection in plan | ER | Covered by mutating_sql + validator |

---

## 11. Planned `cases.json` fields

```json
{
  "id": "risk_summary_table",
  "techniques": ["DT", "EP"],
  "dt_pattern": "PAT-RISK",
  "ep_partition": "EP-FILTER-VIEW",
  "layer": "pipeline",
  "question": "Which students are at risk this term? Show as a table.",
  "sql_must_contain": ["student_risk_summary"],
  "expected": {
    "artifact_type": "table",
    "min_row_count": 1,
    "row_count": 5
  }
}
```

**sql_only variant:**

```json
{
  "id": "boundary_high_risk_score",
  "techniques": ["BR"],
  "layer": "sql_only",
  "sql": "SELECT student_name, avg_score FROM student_risk_summary WHERE avg_score < 70",
  "expected": {
    "min_row_count": 1,
    "row_assertions": { "all": { "avg_score": { "lt": 70 } } }
  }
}
```

---

## 12. Open questions

1. **Row matching:** strict full rows vs key columns for v1?
2. **Views only** vs allow raw-table joins in pass criteria?
3. **Split runners:** `run_eval.py --layer sql_only` (CI) vs `--layer pipeline` (LM Studio)?
4. Bad SQL **generation** failure — fail `sql/` or also count as planning failure?

---

## 13. Review checklist

- [ ] DT patterns PAT-RISK … PAT-ASSESS each have ≥1 case
- [ ] EP: 8 partitions covered
- [ ] BR: sql_only cases with no LLM dependency
- [ ] ER: validator tests without LM Studio
- [ ] LLM scope documented: step 1 SQL only, not step 2
- [ ] ST explicitly deferred to integration
- [ ] Ready for `sql/cases.json`

## Related documents

- [planning.md](planning.md) — `needs_sql` routing (upstream)
- [chart.md](chart.md) — when artifact is chart not table
- [integration.md](integration.md) — replan (ST), E2E
- [SHARED_RUBRICS.md](SHARED_RUBRICS.md) — risk ground truth
