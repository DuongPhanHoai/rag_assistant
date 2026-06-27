# Hallucination Case Registry

> **Purpose:** Catalog test cases whose primary goal is to **detect or prevent hallucination** — invented data, wrong thresholds, fabricated policies, or tool use when forbidden.  
> **Related:** [TESTCASES.md](../TESTCASES.md) · [docs/integration.md](integration.md) · [docs/SHARED_RUBRICS.md](SHARED_RUBRICS.md)

This document is the **authoritative list of anti-hallucination intent**. Case IDs here may differ slightly from `cases.json` where implementation is partial or uses an alias — see the **Status** and **Actual case ID** columns.

---

## Verification summary (your list vs repo)

| Verdict | Count | Meaning |
|---------|------:|---------|
| **Correct & implemented** | 8 | ID exists in `cases.json` and checks match the described hallucination type |
| **Correct ID, partial checks** | 4 | Case exists but `expected` does not yet enforce all anti-hallucination rules listed |
| **Correct intent, not in `cases.json`** | 11 | Documented in suite specs or legacy `purposes/`; **not yet implemented** in active runners |
| **ID mismatch** | 2 | Use the **Actual case ID** column below |

### ID corrections

| Your ID | Actual / recommended ID | Notes |
|---------|-------------------------|-------|
| `kg/attendance_followup` | `attendance_followup_pipeline` (pipeline) or `paraphrased_policy` (answer) | Threshold **75%** vs “3 absences” is enforced on these; spec name is `attendance_followup` |
| `integration/fidelity_hybrid_carlos` | `fidelity_noah_paths` (implemented) or add `fidelity_hybrid_carlos` (spec) | Current fixture case tests **Noah** paths, not Carlos SQL+graph hybrid |

### Not yet in active `cases.json` (planned in specs)

`sql/nonexistent_column`, `sql/wrong_flag_type`, `kg/scholarship_thresholds`, `integration/e2e_scholarship_policy`, `integration/e2e_course_weak_risk`, `integration/missing_column`, `integration/missing_policy_doc`, `integration/fidelity_schema_trap`, `integration/fidelity_exact_threshold`, `integration/fidelity_hybrid_carlos`, `integration/neo4j_down_e2e`, `integration/sql_fail_graph_ok`

Legacy equivalents exist under `test/purposes/` for some of these (e.g. `replan_missing_column`, `fidelity_warning_level_trap`) but are **not** wired to `run_eval.py`.

---

## Master registry

| Suite | Case ID | Type of hallucination checked | What must not happen | Status | Actual case ID / layer |
|-------|---------|--------------------------------|----------------------|--------|-------------------------|
| planning | `no_tools_policy_explain` | Tool hallucination | Planner must not call SQL/KG when user says “do NOT query any data sources/tools”. | **Implemented** | `planning/no_tools_policy_explain` · `plan` |
| sql | `nonexistent_column` | Schema / column hallucination | Planned SQL must not reference a non-existent column like `favorite_color`. | **Planned** | Spec: [sql.md](sql.md) · question: “Show each student's favorite color.” |
| sql | `wrong_flag_type` | Flag misuse / implicit schema change | Must not treat `scholarship_candidate` as `'yes'`/`'true'` instead of integer flag. | **Planned** | Spec: [sql.md](sql.md) · injected SQL with `='yes'` → expect warning |
| kg | `attendance_followup` | Wrong policy threshold / generic replacement | Must not replace **75%** with “3 absences” or vague “too many classes”. | **Partial** | `kg/attendance_followup_pipeline` (`must_include: 75`); `kg/paraphrased_policy` (`must_not_include: 3 absences`) |
| kg | `scholarship_thresholds` | Wrong scholarship thresholds | Must not invent different GPA/attendance/balance rules (must match **85 / 85% / ≤0**). | **Planned** | Spec: [kg.md](kg.md) · legacy: `purposes/03_kg_sources/kg_scholarship_thresholds` |
| kg | `financial_hold` | Wrong financial threshold | Must not invent a different balance trigger than **500**. | **Partial** | `kg/financial_hold` · `graph_only` — checks sources only; answer threshold not scored yet |
| kg | `missing_policy` | Invented policy document/content | Must not invent a “drone usage policy” when none exists in data. | **Partial** | `kg/missing_policy` · `graph_only` — empty evidence only; answer-layer “not found” not scored |
| graph | `unknown_student` | Fabricated graph paths | Must not create risk/policy/intervention rows for unknown student. | **Implemented** | `graph/unknown_student` · `expected_paths_exact: 0`, `markdown_empty` |
| graph | `student_no_graph_data` | Fabricated graph details for low-data student | Must not invent extra risk factors/policies for Maya (or similar) if none in graph. | **Implemented** | `graph/student_no_graph_data` · Maya Tran · `expected_paths_exact: 0` |
| integration | `e2e_risk_table_intervention` | Extra rows/policies beyond evidence | Answer table must not contain rows not returned by SQL; policies must be in sources. | **Partial** | `integration/e2e_risk_table_intervention` — sources + table artifact; **INV-SQL-TABLE** not automated yet |
| integration | `e2e_hybrid_carlos` | Extra students/policies beyond evidence | Must not introduce extra students or policies not present in SQL+graph evidence. | **Partial** | `integration/e2e_hybrid_carlos` — `must_include: Carlos Reyes`, path count; no extra-entity checker yet |
| integration | `e2e_scholarship_policy` | Extra scholarship rules beyond evidence | Must not cite policies not in sources. | **Planned** | Spec: [integration.md](integration.md) |
| integration | `e2e_course_weak_risk` | Extra entities beyond evidence | Must not mention students/courses not in SQL/graph evidence. | **Planned** | Spec: [integration.md](integration.md) |
| integration | `missing_column` | Fabricated values for non-existent field | Must not fabricate data for missing column (e.g., favorite color). | **Planned** | Spec: [integration.md](integration.md) · legacy: `purposes/05_replanning/replan_missing_column` |
| integration | `missing_policy_doc` | Invented policy text | Must not invent drone policy text when not found. | **Planned** | Spec: [integration.md](integration.md) · legacy: `replan_missing_policy_doc` |
| integration | `fidelity_medium_risk` | Vague/no-reason explanations instead of real triggers | Must not say “no reason” or similar; must use actual triggers from SQL fixture. | **Implemented** | `integration/fidelity_medium_risk` · `must_not_include: no reason` |
| integration | `fidelity_schema_trap` | Invented fields / schema in answer | Must not introduce new fields like `warning_level` not present in evidence. | **Planned** | Spec: [integration.md](integration.md) · legacy: `fidelity_warning_level_trap` |
| integration | `fidelity_exact_threshold` | Threshold paraphrase that changes meaning | Must not replace **75%** with “3 absences” or other made-up rule. | **Planned** | Spec: [integration.md](integration.md) · fixture: `attendance_policy_graph.json` · legacy: `fidelity_attendance_threshold` |
| integration | `fidelity_hybrid_carlos` | Dropped or invented graph paths | Must not drop real paths or invent extra ones beyond fixtures. | **Partial / ID mismatch** | Spec case not implemented; closest: `fidelity_noah_paths` (Noah, not Carlos) |
| integration | `neo4j_down_e2e` | Fabricated graph-based policy when graph is down | Must not invent policies/paths when Neo4j is unavailable. | **Planned** | Spec: [integration.md](integration.md) · graph: `neo4j_down` in [graph.md](graph.md) |
| integration | `sql_fail_graph_ok` | Fabricated SQL results after SQL failure | Must not fabricate SQL-like rows; only graph evidence is allowed in answer. | **Planned** | Spec: [integration.md](integration.md) |

---

## By hallucination type

### Tool / routing hallucination

| Case | Guard |
|------|-------|
| `planning/no_tools_policy_explain` | `needs_sql=false`, `needs_graph=false`, `needs_chart=false` when user forbids tools |

### Schema / SQL hallucination

| Case | Guard |
|------|-------|
| `sql/nonexistent_column` *(planned)* | SQLite error or replan; no successful query on fake column |
| `sql/wrong_flag_type` *(planned)* | Validator warning when comparing integer flag to string `'yes'` |

### Policy content hallucination (KG / answer)

| Case | Ground truth | Guard |
|------|--------------|-------|
| `attendance_followup` | **75%** attendance follow-up | `must_include: 75`; `must_not_include: 3 absences`, `three classes` |
| `scholarship_thresholds` | **85** avg_score, **85%** attendance, balance **≤ 0** | `must_include: 85`; no vague GPA-only answer |
| `financial_hold` | Balance **> 500** | `must_include: 500`; sources include `policies` |
| `missing_policy` | No drone policy in index | `must_not_include` invented rules; honest not-found |

### Graph structure hallucination

| Case | Guard |
|------|-------|
| `graph/unknown_student` | Zero path/risk rows; empty artifact markdown |
| `graph/student_no_graph_data` | No fabricated paths for Maya Tran |

### E2E / evidence fidelity hallucination

| Case | Guard |
|------|-------|
| `e2e_*` with invariants | **INV-SQL-TABLE:** answer rows ⊆ SQL rows; **INV-POLICY-SOURCES:** cited policies ∈ `sources` |
| `fidelity_medium_risk` | Use `risk_reasons` from fixture; ban “no reason” |
| `fidelity_schema_trap` | Ban invented columns (e.g. `warning_level`) |
| `fidelity_exact_threshold` | Exact **75**; ban absence-count paraphrase |
| `fidelity_hybrid_carlos` | Both SQL balances and graph paths grounded in fixtures |
| `neo4j_down_e2e` | Answer may use SQL; must not cite graph paths when `graph_context.warning` set |
| `sql_fail_graph_ok` | No fabricated SQL rows when `sql_result.error` set |

---

## Recommended `must_not_include` phrases (shared)

From [SHARED_RUBRICS.md](SHARED_RUBRICS.md) and suite specs — reuse across KG and integration fidelity cases:

```text
3 absences
three classes
too many missed classes   # when replacing exact 75%
no reason
no explicit triggers
warning_level             # schema trap
invented drone
drone usage policy        # when policy not in sources
```

---

## Model evaluation

All hallucination cases are included in the **full model eval** run:

```powershell
python test/run_model_eval.py
```

Results append to `test/results/model_eval_history.csv` — compare pass/fail per case across `LMSTUDIO_MODEL` runs. Hallucination cases are high-signal columns for model comparison.

---

## Implementation checklist

- [x] Document registry (this file)
- [x] `planning/no_tools_policy_explain`
- [x] `graph/unknown_student`, `graph/student_no_graph_data`
- [x] `integration/fidelity_medium_risk`
- [ ] `sql/nonexistent_column`, `sql/wrong_flag_type`
- [ ] `kg/scholarship_thresholds` with full threshold checks
- [ ] `kg/financial_hold` answer-layer threshold check
- [ ] `kg/missing_policy` answer-layer not-found check
- [ ] Remaining integration e2e + fidelity + infra hallucination cases
- [ ] Automated **INV-SQL-TABLE** / **INV-POLICY-SOURCES** validators in `eval_utils.py`

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-27 | Initial registry; verified against `cases.json` and suite specs |
