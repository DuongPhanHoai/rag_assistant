# Running Tests — Guide

Operational guide for the student-agent eval framework. Specs and technique matrices live in [TESTCASES.md](TESTCASES.md) and [docs/](docs/).

---

## Prerequisites

1. **Build data** (once, or after CSV changes):

   ```powershell
   python scripts/build_student_db.py
   python scripts/build_student_kg.py
   ```

2. **Environment** — copy `.env.example` to `.env` and set:

   | Variable | Required for | Notes |
   |----------|--------------|-------|
   | SQLite DB | All suites | Created by `build_student_db.py` |
   | Neo4j | `graph/`, `kg/`, most `integration/` | KG must be loaded |
   | `LLM_ONLINE_MODE=true` | LLM cases | LM Studio (or configured provider) running |
   | `LLM_ONLINE_MODE=false` | Deterministic + `offline_mode` | No LM Studio needed |

3. **Optional fixtures** (for frozen evidence used in docs / fidelity):

   ```powershell
   python test/scripts/build_fixtures.py
   ```

---

## Entry point

All suites use one runner:

```powershell
python test/run_eval.py [options]
```

### Model evaluation (full run + CSV history)

Single trigger to run **all cases** and record results for model comparison:

```powershell
python test/run_model_eval.py
# or
python test/run_eval.py --model-eval
```

Reads `LMSTUDIO_MODEL` from `.env`, runs every case across all six suites, and appends a new column to the history CSV. Re-run after changing the model to compare side-by-side.

### Hallucination evaluation (human review)

Run only anti-hallucination cases and log full answers for manual model comparison:

```powershell
python test/run_hallucination_eval.py
# or
python test/run_eval.py --hallucination-eval
```

See [docs/HALLUCINATION_CASES.md](docs/HALLUCINATION_CASES.md) and `hallucination_eval_answers.csv`.

Legacy wrappers delegate to the same runner:

```powershell
python test/planning/run_eval.py [--case <id>]
python test/run_plan_eval.py [--case <id>]
```

---

## Run one case at a time

Use `--case` with the case **id** from `cases.json`:

```powershell
# Finds the case in any suite
python test/run_eval.py --case noah_irregular_attendance
python test/run_eval.py --case sql_only_risk
python test/run_eval.py --case risk_summary_table

# Narrow to a suite (recommended when ids might overlap)
python test/run_eval.py --suite graph --case carlos_intervention_paths
python test/run_eval.py --suite planning --case ambiguous_graph_word
python test/run_eval.py --suite sql --case top_by_avg_score
```

List ids before running:

```powershell
python test/run_eval.py --list
python test/run_eval.py --list --suite sql
```

---

## Run a full suite

```powershell
python test/run_eval.py --suite planning
python test/run_eval.py --suite sql
python test/run_eval.py --suite graph
python test/run_eval.py --suite chart
python test/run_eval.py --suite kg
python test/run_eval.py --suite integration
```

Repeat `--suite` to run several suites in one invocation:

```powershell
python test/run_eval.py --suite sql --suite graph --suite chart
```

Run **everything** (omit `--suite`):

```powershell
python test/run_eval.py
```

---

## Filter by layer

Cases declare a `layer` field in JSON (e.g. `sql_only`, `graph_only`, `pipeline`, `e2e`):

```powershell
python test/run_eval.py --suite sql --layer sql_only
python test/run_eval.py --suite graph --layer graph_only
python test/run_eval.py --suite integration --layer fidelity
```

Combine with `--case` when a case id is unique.

---

## CI / no-LLM runs

Skip cases that need LM Studio:

```powershell
python test/run_eval.py --no-llm-only
```

This runs **20 deterministic cases** across `sql`, `graph`, `chart`, and `kg` (plus skips LLM-only integration cases). Useful for quick regression without a live LLM.

Per-suite no-LLM examples:

```powershell
python test/run_eval.py --suite sql --layer sql_only
python test/run_eval.py --suite graph
python test/run_eval.py --suite chart --layer artifact_only
python test/run_eval.py --suite kg --layer graph_only
```

---

## LLM runs

Set online mode and ensure the LLM endpoint is reachable:

```powershell
$env:LLM_ONLINE_MODE = "true"
python test/run_eval.py --suite planning
python test/run_eval.py --case sql_only_risk
python test/run_eval.py --suite integration --layer e2e
```

LLM cases that cannot run offline show **`[SKIP]`** with a message instead of failing the run.

### Offline mode integration case

`integration/offline_mode` expects LLM **disabled**:

```powershell
$env:LLM_ONLINE_MODE = "false"
python test/run_eval.py --case offline_mode
```

---

## CLI reference

| Flag | Description |
|------|-------------|
| `--list` | Print all suites and case ids; no tests run |
| `--suite <name>` | Limit to suite(s): `planning`, `sql`, `graph`, `chart`, `kg`, `integration` |
| `--case <id>` | Run a single case by id |
| `--layer <name>` | Filter by case `layer` |
| `--no-llm-only` | Run only cases that do not require `LLM_ONLINE_MODE=true` |
| `--model-eval` | Run all cases and append to `model_eval_history.csv` (same as `run_model_eval.py`) |
| `--hallucination-eval` | Hallucination cases + answer log for human review (same as `run_hallucination_eval.py`) |

Exit code: **0** if no failures; **1** if any case failed or no case matched filters. Skipped LLM cases do not fail the run.

---

## Results

Each run appends one JSONL record per case:

```text
test/results/planning_results.jsonl
test/results/sql_results.jsonl
test/results/graph_results.jsonl
test/results/chart_results.jsonl
test/results/kg_results.jsonl
test/results/integration_results.jsonl
```

Fields include `run_id`, `status` (`pass` / `fail` / `skip`), `duration_seconds`, `failures`, and suite-specific payloads. JSONL files under `results/` are gitignored.

### Model evaluation history (CSV)

Use **`run_model_eval.py`** when comparing models across runs:

| File | Purpose |
|------|---------|
| `test/results/model_eval_history.csv` | **Wide matrix** — one row per test case; each run adds a column `{LMSTUDIO_MODEL} @ {UTC timestamp}` |
| `test/results/model_eval_runs.csv` | **Run log** — model name, timestamps, pass/fail/skip totals, total duration |

**Cell format:** `pass (2.3s)`, `fail (1.1s)`, or `skip (0.0s)`

**Fixed columns** (always present): `suite`, `case_id`, `layer`, `requires_llm`

**Workflow — compare two models:**

```powershell
# 1. Load model A in LM Studio, set .env
# LMSTUDIO_MODEL=google/gemma-4-e4b
python test/run_model_eval.py

# 2. Load model B, update .env
# LMSTUDIO_MODEL=google/gemma-4-12b-qat
python test/run_model_eval.py

# 3. Open model_eval_history.csv — each model run is a column
```

### Hallucination evaluation history (CSV)

Use **`run_hallucination_eval.py`** when comparing **answer content** with human review:

| File | Purpose |
|------|---------|
| `test/results/hallucination_eval_history.csv` | Pass/fail matrix (hallucination cases only) |
| `test/results/hallucination_eval_answers.csv` | Full `review_text` per case + `human_verdict` / `human_notes` columns |
| `test/results/hallucination_eval_runs.csv` | Run metadata |

```powershell
python test/run_hallucination_eval.py
# Change LMSTUDIO_MODEL and re-run; compare review_text for same case_id across runs
```

---

## Suite quick reference

| Suite | Cases | No-LLM layer | LLM layer | Spec |
|-------|------:|--------------|-----------|------|
| planning | 19 | — | `plan` | [docs/planning.md](docs/planning.md) |
| sql | 7 | `sql_only` | `pipeline` | [docs/sql.md](docs/sql.md) |
| graph | 7 | `graph_only` | `pipeline`, `answer` | [docs/graph.md](docs/graph.md) |
| chart | 5 | `artifact_only` | `pipeline`, `answer` | [docs/chart.md](docs/chart.md) |
| kg | 5 | `graph_only` | `pipeline`, `answer` | [docs/kg.md](docs/kg.md) |
| integration | 6 | `infra` (`offline_mode`) | `e2e`, `fidelity`, `replan` | [docs/integration.md](docs/integration.md) |

---

## Suggested workflows

**Local quick check (no LLM):**

```powershell
python test/run_eval.py --no-llm-only
```

**Before changing planner prompts:**

```powershell
python test/run_eval.py --suite planning
```

**Debug one failing graph path:**

```powershell
python test/run_eval.py --suite graph --case carlos_intervention_paths
```

**Full pre-release (LLM + data required):**

```powershell
$env:LLM_ONLINE_MODE = "true"
python test/run_model_eval.py
```

**Compare models over time:**

```powershell
# After each model swap in LM Studio + .env update:
python test/run_model_eval.py
# Inspect test/results/model_eval_history.csv
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Neo4j / connection errors on graph or kg | KG not built or Neo4j down | Run `build_student_kg.py`; check Neo4j |
| SQL “no such table/column” | Stale SQLite | Run `build_student_db.py` |
| `[SKIP] … requires LLM` | `LLM_ONLINE_MODE=false` | Set `true` or use `--no-llm-only` intentionally |
| `No case found with id` | Typo or wrong suite | `python test/run_eval.py --list` |
| Planning cases flaky | LLM routing variance | Re-run single case; check `planning_results.jsonl` |

---

## Adding a case

1. Read the suite spec under [docs/](docs/).
2. Add an object to `test/<suite>/cases.json` with at least `id`, `layer`, `question`, and `expected`.
3. List and run it:

   ```powershell
   python test/run_eval.py --list --suite <suite>
   python test/run_eval.py --suite <suite> --case <new_id>
   ```

Shared validators and schema notes: [docs/SHARED_RUBRICS.md](docs/SHARED_RUBRICS.md).
