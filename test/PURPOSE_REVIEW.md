# Test Purpose Review

Your seven categories are a strong eval framework. This document maps each category to **this repository's actual architecture**, notes gaps, and defines how cases are isolated under `test/purposes/`.

## Architecture mapping (your terms → this project)

| Your idea | This project | Notes |
|-----------|--------------|-------|
| SQLite tool | `run_sql()` via `needs_sql` + planned SQL | Read-only validation in `db.py` |
| Chroma / embeddings | **Neo4j knowledge graph** (`get_graph_evidence()`) | Policies come from CSV → SQLite tables + Neo4j nodes/edges. **No Chroma in student-agent.** |
| Tool-calling loop | `student-lmstudio-agent` (separate entry point) | `student-agent` uses a **two-step LLM** workflow, not per-turn tool calls |
| GPA | `avg_score` in `student_risk_summary` | Not named `gpa` |
| CS101 | `C101` (Database Fundamentals) | Course IDs are `C101`–`C105` |
| Document source | `source_doc` / `source_data` labels | e.g. `policies`, `student_risk_factors` — not PDF page numbers |
| LLM step 1 | `plan_question()` | Sets `needs_sql`, `needs_graph`, `needs_chart`, writes SQL |
| LLM step 2 | `answer_from_evidence()` | Synthesizes from frozen or live evidence |

## What each purpose category tests here

### 1. Planning & decomposition

**Your goal:** LLM recognizes when to use tools instead of guessing.

**Here:** Test **Step 1 only** (`plan_question`) or plan flags on full pipeline.

| Sub-case | Adapted prompt | Expect |
|----------|----------------|--------|
| SQL-only | List all students enrolled in C101. | `needs_sql=true`, `needs_graph=false`; SQL hits `enrollments` + `students` |
| KG-only | Explain the attendance policy for missing more than 3 classes. | `needs_graph=true` (or SQL on `policies` — both valid if grounded); **must not invent** thresholds not in data |
| Combined | Which students are at risk based on avg_score and what interventions do policy documents recommend? | `needs_sql=true`, `needs_graph=true` |

**Gap:** Deterministic agent does not expose separate "tool call" traces — assert on **plan flags** and executed evidence (`sql_result`, `graph_context`).

---

### 2. SQL query use & table output

**Your goal:** Correct SQL and tabular formatting.

**Here:** Test **plan SQL** + **deterministic execution** + **artifact type `table`**. Answer LLM is optional.

| Sub-case | Adapted prompt | Expect |
|----------|----------------|--------|
| Aggregation | Show the number of students per course as a table sorted by most popular course. | `GROUP BY` on enrollments; columns include `course_id`, count |
| Filter + sort | List the top 3 students by avg_score with program and advisor. | `ORDER BY avg_score DESC LIMIT 3`; rows match SQLite ground truth |

**Gap:** Table markdown is built by `generate_table_or_chart_spec()`, not the LLM — score **SQL correctness** and **row match**, not LLM table formatting.

---

### 3. RAG / KG retrieval & source grounding

**Your goal:** Use retrieved evidence, not prior knowledge; show sources.

**Here:** Replace Chroma with **Neo4j graph** (+ optional SQL `policies` table).

| Sub-case | Adapted prompt | Expect |
|----------|----------------|--------|
| Precise policy | What is the minimum avg_score required to keep scholarship support, and what happens if a student falls below it? | Answer cites **85** and **85% attendance** from Scholarship Support Policy; sources include `policies` |
| Multi-source | Summarize advisor responsibilities for at-risk students from policy documents. | Graph/SQL hits `Intervention Playbook`, `Academic Risk Policy`; multiple `source_doc` values |

**Ground truth:** `data/student_management/policies.csv`, `policy_rules.csv`, Neo4j paths.

---

### 4. Chart vs table decision

**Your goal:** LLM chooses visualization appropriately.

**Here:** Assert `needs_chart` in plan + `artifact.type == "chart"` with Vega-Lite spec.

| Sub-case | Adapted prompt | Expect |
|----------|----------------|--------|
| Time series – chart | Show attendance trend by month for at-risk students as a chart. | `needs_chart=true`; SQL uses `attendance_trend`; chart spec has `month`, `attendance_pct` |
| Distribution – chart | Visualize risk_level distribution across all students. | SQL with counts per `risk_level`; bar chart spec |
| Tabular summary | Show each course with average score and number of students. | `needs_chart=false`; table from `course_performance_summary` |

---

### 5. Replanning when evidence is missing

**Your goal:** Detect missing data and adjust.

**Here:** **Partially supported.** `replan_if_needed()` only re-runs when SQL returns **zero rows** — it does not inspect schema for missing columns.

| Sub-case | Adapted prompt | Expect (realistic) |
|----------|----------------|---------------------|
| Missing column | Show each student's favorite color. | SQL fails or returns empty; answer/step 2 says field not available — **do not invent** |
| Partially answerable | Which students plan to change major next year? | Explain future intent not stored; optional SQL on current `program` |
| No matching doc | What is the university drone usage policy on campus? | Empty graph search; answer states policy not found in indexed sources |

**Gap:** Schema-aware "column does not exist" is not a dedicated replan path today — eval documents **desired behavior** for answer step.

---

### 6. Hallucination control & source fidelity

**Your goal:** Answers match retrieved records exactly.

| Sub-case | Adapted prompt | Expect |
|----------|----------------|--------|
| Conflict trap | According to policy documents, what exact attendance percentage requires advisor follow-up? | **75%** (Attendance Intervention Policy) — not a generic "3 absences" |
| Schema trap | List the warning_level for each student. | No invented column; map to `risk_level` if explained, or state field missing |

**Best layer:** Step 2 with **frozen fixtures** (`test/fixtures/`) so scoring is deterministic.

---

### 7. End-to-end scenario

**Your goal:** Full workflow path.

**Here:** `answer_student_question()` — plan → SQL → graph → artifact → answer.

**Example prompt:** Identify students at risk this term, show them in a table with advisor, and summarize intervention policy for the highest-risk cases.

**Expect:** Plan with SQL + graph; table with Owen/Carlos/Lina; graph paths; sources; no medium-risk described as "no reason".

---

## Recommended isolation model

Two orthogonal axes:

```text
Purpose (what capability)     Layer (what code runs)
─────────────────────────     ──────────────────────
01 planning                   plan      → plan_question only
02 sql_tables                 pipeline  → plan + run_sql + artifact
03 kg_sources                 pipeline  → plan + get_graph_evidence + sources
04 chart_vs_table             pipeline  → plan + artifact type
05 replanning                 pipeline  → full through replan_if_needed
06 fidelity                   answer    → answer_from_evidence + fixtures
07 end_to_end                 e2e       → answer_student_question
```

Existing `test/llm_plan_cases.json` and `test/llm_answer_cases.json` remain the **LLM-step** slice. Purpose folders hold **capability** slices (may span one or both LLM steps).

## Directory layout

```text
test/
  PURPOSE_REVIEW.md           # This file
  TESTCASES.md                # Index + how to run
  purposes/
    01_planning/cases.json
    02_sql_tables/cases.json
    03_kg_sources/cases.json
    04_chart_vs_table/cases.json
    05_replanning/cases.json
    06_fidelity/cases.json
    07_end_to_end/cases.json
  llm_steps/                  # moved conceptually; files at test/ root today
  fixtures/
  run_purpose_eval.py         # Run one or all purpose categories
```

## Scoring fields (every case)

| Field | Meaning |
|-------|---------|
| `layer` | `plan`, `pipeline`, `answer`, `e2e` |
| `expected.flags` | `needs_sql`, `needs_graph`, `needs_chart` |
| `expected.artifact_type` | `table` or `chart` |
| `sql_must_contain` | Fragments in planned SQL |
| `must_include` / `must_not_include` | Answer text rules |
| `expected_sources` | Source labels from graph/SQL |
| `fixture_refs` | Frozen evidence for answer-layer cases |

## Prompts to avoid in this repo

These do not match the seed data or schema:

- `GPA` without mapping to `avg_score`
- `CS101` → use `C101`
- Expecting Chroma / embedding tool names
- `warning_level`, `favorite color`, `total credits` (not in schema unless added)
- "Missing assignments" as a column — use `assessment_scores` or risk views instead

## Next steps

1. Run by purpose: `python test/run_purpose_eval.py --purpose 01_planning`
2. Regenerate fixtures: `python test/scripts/build_fixtures.py`
3. Add cases under `test/purposes/<category>/cases.json` using the schema in `test/purpose_schema.json`
