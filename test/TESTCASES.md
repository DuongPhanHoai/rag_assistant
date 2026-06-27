# Test Cases — Index

> **Status:** Implemented — six suites with `cases.json` and unified runner.  
> **How to run:** [RUNNING_TESTS.md](RUNNING_TESTS.md)

## Purpose

Organize student-agent evaluation by **capability** (six suites) with independent specification documents under `test/docs/`.

## Directory layout

```text
test/
  TESTCASES.md                 ← this index
  RUNNING_TESTS.md             ← runner guide (single case, CI, LLM)
  run_eval.py                  ← unified CLI
  eval_utils.py                ← shared validators
  suites/
    runner.py                  ← list / filter / orchestrate
    evaluators.py              ← per-suite evaluation
  docs/
    ARCHITECTURE.md
    MODEL_EVALUATION.md        ← comparing LLMs: scope, metrics, weighted score
    SHARED_RUBRICS.md
    planning.md … integration.md
  planning/cases.json          (19 cases)
  sql/cases.json               (7 cases)
  graph/cases.json             (7 cases)
  chart/cases.json             (5 cases)
  kg/cases.json                (5 cases)
  integration/cases.json       (6 cases)
  fixtures/
  scripts/build_fixtures.py
  results/                     ← gitignored JSONL output
```

Legacy assets (still present; prefer `run_eval.py`):

- `llm_plan_cases.json`, `llm_answer_cases.json`, `purposes/`, `run_purpose_eval.py`, `run_answer_eval.py`
- `run_plan_eval.py`, `planning/run_eval.py` — thin wrappers around `run_eval.py --suite planning`

Repo-root batch eval: `eval/student_questions.json` + `eval_student_run.py`

---

## Quick start

```powershell
# List all cases
python test/run_eval.py --list

# Run one case
python test/run_eval.py --case noah_irregular_attendance

# Deterministic CI subset (no LM Studio)
python test/run_eval.py --no-llm-only

# Full suite
python test/run_eval.py --suite planning
```

Full CLI, prerequisites, layers, and troubleshooting: **[RUNNING_TESTS.md](RUNNING_TESTS.md)**

### Model comparison (CSV history)

**Guide:** [docs/MODEL_EVALUATION.md](docs/MODEL_EVALUATION.md) — what the suite measures, gaps, weighted scoring.

Run **all 49 cases** for the current `LMSTUDIO_MODEL` and append a column to the history matrix:

```powershell
# Set model in .env, then:
python test/run_model_eval.py
# equivalent:
python test/run_eval.py --model-eval
```

Outputs:

- `test/results/model_eval_history.csv` — rows = cases, columns = `{LMSTUDIO_MODEL} @ {timestamp}` with `pass` / `fail` / `skip` (+ duration)
- `test/results/model_eval_runs.csv` — one row per run with aggregate pass/fail/skip counts

Switch `LMSTUDIO_MODEL` in `.env` and re-run to build comparison columns side-by-side.

Generate HTML comparison report (charts + pass % + timing):

```powershell
python test/scripts/generate_model_eval_report.py
# opens: test/results/model_eval_report.html
```

Hallucination-focused runs with full answers for human review: [docs/HALLUCINATION_CASES.md](docs/HALLUCINATION_CASES.md) · `python test/run_hallucination_eval.py`

---

## Agent flow (summary)

```text
Question → planning → sql / kg / graph / chart → integration (answer + E2E)
              │              └── deterministic retrieval
              └── LLM step 1: plan_question()
                                    └── LLM step 2: answer_from_evidence()
```

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Suite index

| Suite | Document | Question answered | Layer | Cases |
|-------|----------|-------------------|-------|------:|
| **Planning** | [docs/planning.md](docs/planning.md) | Did the planner route to SQL / graph / chart? | `plan` | 19 |
| **SQL** | [docs/sql.md](docs/sql.md) | Is SQL correct and the table grounded? | `sql_only`, `pipeline` | 7 |
| **KG** | [docs/kg.md](docs/kg.md) | Are policy facts retrieved with sources? | `graph_only`, `pipeline`, `answer` | 5 |
| **Chart** | [docs/chart.md](docs/chart.md) | Chart vs table + Vega-Lite spec? | `artifact_only`, `pipeline`, `answer` | 5 |
| **Graph** | [docs/graph.md](docs/graph.md) | Student → policy → intervention paths? | `graph_only`, `pipeline`, `answer` | 7 |
| **Integration** | [docs/integration.md](docs/integration.md) | Full workflow, replan, fidelity? | `e2e`, `fidelity`, `replan`, `infra` | 6 |

Shared rubrics, schema, fixtures: [docs/SHARED_RUBRICS.md](docs/SHARED_RUBRICS.md)

Anti-hallucination registry (verified case list): [docs/HALLUCINATION_CASES.md](docs/HALLUCINATION_CASES.md)

Human review eval: `python test/run_hallucination_eval.py` → `test/results/hallucination_eval_answers.csv`

---

## kg vs graph (summary)

| | **kg/** | **graph/** |
|---|---------|------------|
| Focus | Policy **content** & sources | Relationship **paths** |
| Example | “Minimum avg_score for scholarship is 85” | “Noah → Irregular Attendance → … → Weekly Lab Attendance” |

---

## Testing techniques (by suite)

| Technique | Planning | SQL | KG | Chart | Graph | Integration |
|-----------|:--------:|:---:|:--:|:-----:|:-----:|:-----------:|
| Decision table (DT) | ● | ● | ● | ● | ● | ○ |
| Equivalence partition (EP) | ● | ● | ● | ● | ● | ● |
| Boundary / range (BR) | — | ● | ● | ○ | ●† | ● |
| Exceptional (EX) | ● | ● | ● | ● | ● | ● |
| Error (ER) | ● | ● | ● | ● | ● | ● |
| State change (ST) | ○ | — | — | — | — | ● |

● primary · ○ partial · — not used · † path count (1 vs 2), not numeric thresholds

Technique definitions: [docs/SHARED_RUBRICS.md](docs/SHARED_RUBRICS.md#testing-technique-legend)

## LLM evaluation (by suite)

| Suite | LLM step 1 (plan) | LLM step 2 (answer) | No-LLM layer |
|-------|:-----------------:|:-------------------:|--------------|
| **planning** | **Always** (flags only) | No | — |
| **sql** | Optional (`pipeline`) | No | **`sql_only`** (validator + rows) |
| **kg** | Optional (`pipeline`) | **`answer` / pipeline** | **`graph_only`** (retrieval) |
| **chart** | Optional (`pipeline`, flag) | Optional (`answer`, description) | **`artifact_only`** (Vega-Lite) |
| **graph** | Optional (`pipeline`) | Optional (`answer`) | **`graph_only`** (paths) |
| **integration** | **Yes (e2e)** | **Yes (e2e + fidelity)** | **`infra`** (`offline_mode`) |

**Only `integration/` routinely scores both LLM steps.** Other suites isolate step 1, step 2, or deterministic retrieval/artifacts.

Details per suite: see **§2 Does this suite evaluate the LLM?** in each doc under [docs/](docs/).

---

## Review workflow (specs)

1. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for terminology and constraints.
2. Review each suite document (suggested order: planning → sql → kg → chart → graph → integration).
3. When adding cases, update `*/cases.json` and run via [RUNNING_TESTS.md](RUNNING_TESTS.md).

---

## Planned (not implemented)

| Item | Design doc |
|------|------------|
| **ETL / data quality suite (`etl/`)** | [docs/ETL_DATA_QUALITY_PLAN.md](../docs/ETL_DATA_QUALITY_PLAN.md) — draft for review |

---

## Resolved decisions

| Topic | Decision |
|-------|----------|
| **Runners** | Single `test/run_eval.py` with `--suite` / `--case` / `--layer` / `--no-llm-only` |
| **Plan strictness** | Option B — normalize plan; strict R2 for policy-only routing (see [planning.md](docs/planning.md)) |
| **kg vs graph** | Split retained — content/sources vs paths |

## Open questions

1. **Fidelity** — Sub-area of `integration/` or seventh suite?
2. **Legacy files** — Merge `llm_plan_cases.json` into `planning/` or keep as alias?
3. **Coverage gaps** — Expand cases toward full traceability tables in each spec doc.

---

## Document changelog

| Date | Change |
|------|--------|
| 2026-06-26 | Split monolithic TESTCASES.md into `test/docs/*.md` index + per-suite specs |
| 2026-06-27 | Implemented suites, unified runner; added [RUNNING_TESTS.md](RUNNING_TESTS.md) |
