# Test Architecture Notes

> Shared context for all test suite documents under `test/docs/`.

## Agent under test

Primary entry: `student-agent` → `answer_student_question()` in `src/student_rag/agents/deterministic.py`.

```text
Question
   │
   ▼
plan_question()              ← LLM step 1 (when LLM_ONLINE_MODE=true)
   │
   ├── run_sql()             ← deterministic
   ├── get_graph_evidence()  ← deterministic (Neo4j)
   ├── replan_if_needed()    ← deterministic
   ├── generate_table_or_chart_spec()
   │
   ▼
answer_from_evidence()       ← LLM step 2
```

## Evidence stores

| Store | Role | Populated from |
|-------|------|----------------|
| SQLite | Structured student metrics, views, `policies` table | CSV via `scripts/build_student_db.py` |
| Neo4j | Policy paths, risk factors, interventions | CSV via `scripts/build_student_kg.py` |

**There is no Chroma / vector store** in the deterministic student agent.

## Terminology mapping

| Generic RAG term | This project |
|------------------|--------------|
| Embeddings / Chroma | Neo4j KG + optional SQL `policies` |
| GPA | `avg_score` in `student_risk_summary` |
| CS101 | `C101` (Database Fundamentals) |
| Document source | `source_doc` / `source_data` (e.g. `policies`, `student_risk_factors`) |
| Tool calls | Plan flags: `needs_sql`, `needs_graph`, `needs_chart` |

## Key views and tables

| Object | Use |
|--------|-----|
| `student_risk_summary` | Risk level, avg_score, attendance_pct, balance_due, scholarship_candidate |
| `course_performance_summary` | Per-course averages and enrollment counts |
| `attendance_trend` | Monthly attendance_pct by student |
| `fee_summary` | Fee balances by term |
| `enrollments` + `students` | Course enrollment lists |
| `policies` | Policy text summaries (SQLite) |

## Planner merge behavior

Online plans merge LLM output with `_fallback_plan()` defaults. Tests should:

- Score **flags** (`needs_*`) as primary routing signals.
- Not require empty SQL when `needs_sql=false` (fallback SQL may still be present in the merged plan).
- Document **acceptable alternates** where SQL-on-`policies` is equivalent to graph retrieval.

## Known limitations

| Behavior | Impact on tests |
|----------|-----------------|
| `replan_if_needed()` | Retries only when SQL returns **zero rows** — not schema-aware |
| Table markdown | Built deterministically — SQL suite scores rows, not LLM formatting |
| Medium-risk `risk_reasons` | Often empty in SQL — answer must infer from thresholds |

## Prerequisites (all suites)

```powershell
python scripts/build_student_db.py
python scripts/build_student_kg.py
python test/scripts/build_fixtures.py   # when fixtures needed
```

`.env`: `LLM_ONLINE_MODE=true` for LLM-involved suites; LM Studio running.

## Out of scope

- `eval/student_questions.json` + `eval_student_run.py` — legacy full-agent batch eval at repo root (unchanged).
- `student-lmstudio-agent` — separate tool-calling loop; optional future suite.
