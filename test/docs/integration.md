# Integration — Test Specification

> **Status:** Review only — no `integration/cases.json` or runner yet.  
> **Suite folder (planned):** `test/integration/`  
> **Layers:** `e2e`, `replan`, `fidelity`, `infra`  
> **Function:** `answer_student_question()` · `answer_from_evidence()` · infra failures

---

## 0. Scope

**Composes all other suites** — full workflow, gaps, hallucination control, and **state / infra** tests deferred elsewhere.

| Sub-area | Focus |
|----------|-------|
| **e2e** | Plan → SQL → graph → artifact → answer |
| **replan** | Missing evidence, empty SQL, schema gaps |
| **fidelity** | LLM step 2 with frozen fixtures |
| **infra** | LM Studio down, Neo4j down, offline mode |

---

## 1. Goal

Validate end-to-end behavior and **cross-cutting** concerns no single suite covers alone.

---

## 2. Does this suite evaluate the LLM?

**Yes — both LLM steps (primary suite that tests full LLM path).**

| Sub-area | Step 1 `plan_question` | Step 2 `answer_from_evidence` | Deterministic parts |
|----------|:----------------------:|:-----------------------------:|---------------------|
| **e2e** | Yes | Yes | SQL, graph, artifact also scored |
| **replan** | Yes | Yes | `replan_if_needed()` deterministic |
| **fidelity** | No (fixtures) | **Yes only** | Frozen evidence |
| **infra** | Yes / fallback | Yes / error | Mode switches |

```text
integration = only suite that routinely scores BOTH LLM calls + replan + infra
```

Other suites isolate one LLM step or skip LLM entirely.

---

## 3. How techniques relate to test cases

| Technique | Applied? | Role in integration |
|-----------|:--------:|---------------------|
| **DT** | Partial | E2E hybrid vs SQL-only vs graph-heavy scenarios |
| **EP** | Yes | Sub-areas: e2e / replan / fidelity / infra |
| **BR** | Via fixtures | 5 at-risk students, exact 75%, medium-risk rules |
| **EX** | Yes | Missing column, drone policy, future major |
| **ER** | Yes | LM down, Neo4j down, SQL fail + graph ok |
| **ST** | **Yes (primary home)** | replan, offline/online mode |

**Integration is the only suite where ST is fully applied.**

---

## 4. Master traceability table

| Case ID | Tech | Sub-area | Layer | LLM step 1 | LLM step 2 | Primary assertion |
|---------|:----:|:--------:|:-----:|:----------:|:----------:|-------------------|
| `e2e_risk_table_intervention` | DT, EP | e2e | e2e | Yes | Yes | Table + policy summary + sources |
| `e2e_hybrid_carlos` | DT, EP | e2e | e2e | Yes | Yes | Balance rank + Carlos paths |
| `e2e_scholarship_policy` | EP | e2e | e2e | Yes | Yes | Candidates + policy |
| `e2e_course_weak_risk` | EP | e2e | e2e | Yes | Yes | Course SQL + graph |
| `missing_column` | EX | replan | e2e | Yes | Yes | No invented favorite color |
| `future_major_change` | EX | replan | e2e | Yes | Yes | Intent not stored |
| `missing_policy_doc` | EX, ER | replan | e2e | Yes | Yes | Drone policy not found |
| `empty_sql_replan` | ST | replan | replan | Yes | — | SQL text/filter differs; 2nd query >0 rows |
| `neo4j_down_e2e` | ER, ST | infra | e2e | Yes | Yes | SQL ok; graph warning |
| `offline_mode` | ST | infra | e2e | No (heuristic) | No | `offline_evidence` |
| `online_mode` | ST | infra | e2e | Yes | Yes | `mode: llm` |
| `lm_down_e2e` | ER | infra | e2e | Fail | — | RuntimeError surfaced |
| `sql_fail_graph_ok` | ER | infra | e2e | Yes | Yes | Graph despite SQL warning |
| `fidelity_medium_risk` | BR, EX | fidelity | answer | No | **Yes** | 5 students; no “no reason” |
| `fidelity_schema_trap` | EX | fidelity | answer | No | **Yes** | warning_level → risk_level |
| `fidelity_exact_threshold` | BR | fidelity | answer | No | **Yes** | Exact 75 |
| `fidelity_hybrid_carlos` | DT | fidelity | answer | No | **Yes** | SQL+graph in one answer |

---

## 5. Sub-area case lists

### 5.1 E2E (`e2e`)

| ID | Prompt | Key checks |
|----|--------|------------|
| `e2e_risk_table_intervention` | At-risk students + advisor table + intervention policy | Owen/Carlos/Lina; sources |
| `e2e_hybrid_carlos` | High-risk balances + Carlos paths | Owen→Carlos→Lina; 2 interventions |
| `e2e_scholarship_policy` | Scholarship candidates + policy | SQL + policy text |
| `e2e_course_weak_risk` | Weak courses + at-risk + graph | Hybrid evidence |

#### 5.1.1 E2E cross-source invariants (optional refinements)

Apply to all `e2e_*` cases where both **SQL table** and **graph/answer policy claims** appear. These catch “looks good in prose” failures.

| Invariant | Check | Fail example |
|-----------|-------|--------------|
| **INV-SQL-TABLE** | Every student named in the structured table (artifact or answer) must appear in `sql_result.rows` (by `student_name` or equivalent key). No table rows **only** from LLM imagination. | Answer lists “Jane Doe” as high risk but SQL has no such row |
| **INV-POLICY-SOURCES** | Every **policy name** cited in the answer (e.g. “Attendance Intervention Policy”, “Financial Hold Policy”) must appear in `result.sources` or in graph/SQL evidence metadata (`source_doc`, `policies` table rows used). | Answer cites “Drone Usage Policy” but `sources` is empty |
| **INV-GRAPH-NAMES** *(hybrid cases)* | Policy/intervention paths mentioned in the answer should match `graph_artifact.path_rows` or `graph_context` when graph was requested. | Carlos answer drops one of two seeded paths |

**Checker sketch (v1 — pragmatic):**

```text
table_names  = { row.student_name for row in sql_result.rows }
answer_names = extract_student_names(answer)  # optional NLP or must_include set
FAIL if ∃ n ∈ answer_names ∩ high_risk_context : n ∉ table_names

policy_phrases = extract_policy_names(answer)  # or must_include from case
actual_sources   = set(result.sources) ∪ policy_names_from_graph_context
FAIL if ∃ p ∈ policy_phrases : p not grounded in sql_result, graph_context, or sources
```

**cases.json hooks (optional):**

```json
{
  "id": "e2e_risk_table_intervention",
  "invariants": ["INV-SQL-TABLE", "INV-POLICY-SOURCES"],
  "table_must_be_subset_of_sql": true,
  "policies_cited_must_be_in_sources": true
}
```

Stronger than `must_include` alone: invariants reference **structured result objects**, not just substring match on answer text.

### 5.2 Replan / missing evidence (`replan`)

| ID | Tech | Expected |
|----|------|----------|
| `missing_column` | EX | No invented data |
| `future_major_change` | EX | Honest gap |
| `missing_policy_doc` | EX | Not found |
| `empty_sql_replan` | **ST** | See §5.2.1 — first vs second SQL must differ; second returns rows |

**Limitation:** replan only on **zero rows**, not schema errors.

#### 5.2.1 `empty_sql_replan` semantics (ST)

Exercises `replan_if_needed()` when the **first** planned SQL returns **0 rows**.

**Pass when all of:**

1. **First SQL** (`plan["sql"]` before replan, or first execution in trace) returns `row_count == 0` *or* case uses injected/mock plan guaranteed to return 0.
2. **Second SQL** (after replan — fallback plan SQL) **differs** from the first in **text** *or* in an identifiable **filter** (e.g. different `WHERE`, broader view, removed over-restrictive predicate).  
   - Fail if identical string re-run.
3. **Second execution** returns **`row_count > 0`** when seed data and case fixtures support it (e.g. replan broadens from impossible filter to `student_risk_summary` default).
4. Final `sql_result` used for artifact/answer is from the **successful** (second) query.

**When (3) cannot be guaranteed** (fragile LLM first plan): mark case as `soft_replan: true` — still require (1) and (2), log row count for manual review.

**Implementation note:** Today replan swaps in `_fallback_plan()` SQL when first result is empty and fallback SQL ≠ first SQL. Eval can compare:

```text
first_sql  = record.plan.sql_before_replan  # runner may capture pre-replan
second_sql = record.plan.sql_after_replan
FAIL if normalize(first_sql) == normalize(second_sql)
FAIL if second_sql_result.row_count == 0  # when soft_replan is false
```

**Optional fixture-driven case:** inject first SQL `SELECT ... WHERE student_name = 'Nonexistent'` → expect fallback heuristic SQL → rows > 0.

### 5.3 Fidelity — LLM step 2 only (`fidelity`)

| ID | Fixtures | must_not_include |
|----|----------|------------------|
| `fidelity_medium_risk` | `risk_summary_sql.json` | `no reason`, `no explicit triggers` |
| `fidelity_schema_trap` | `risk_summary_sql.json` | invented warning_level |
| `fidelity_exact_threshold` | `attendance_policy_graph.json` | `3 absences` |
| `fidelity_hybrid_carlos` | balances + carlos graph | dropped path |

### 5.4 Infra / state (`infra`)

| ID | Tech | Expected |
|----|------|----------|
| `offline_mode` | ST | Heuristic plan; no LM Studio |
| `online_mode` | ST | Full LLM path |
| `lm_down_e2e` | ER | Error, no silent fallback |
| `neo4j_down_e2e` | ER, ST | Partial answer |
| `sql_fail_graph_ok` | ER | Graph evidence still present |

---

## 6. Planned `cases.json` hooks (integration)

```json
{
  "id": "e2e_hybrid_carlos",
  "layer": "e2e",
  "invariants": ["INV-SQL-TABLE", "INV-POLICY-SOURCES", "INV-GRAPH-NAMES"],
  "table_must_be_subset_of_sql": true,
  "policies_cited_must_be_in_sources": true
}
```

```json
{
  "id": "empty_sql_replan",
  "layer": "replan",
  "soft_replan": false,
  "expect_sql_text_change": true,
  "expect_second_row_count_min": 1
}
```

---

## 7. Techniques summary matrix

| Technique | Applied? | # Cases (planned) | LLM? |
|-----------|:--------:|:-----------------:|:----:|
| DT | Partial | 4 e2e + 1 fidelity | Both steps (e2e) |
| EP | Yes | 4 sub-areas | Both steps |
| BR | Yes | 3 fidelity | Step 2 (fixtures) |
| EX | Yes | 6+ | Both steps |
| ER | Yes | 5 | infra + replan |
| ST | **Yes** | 4 | mode + replan |

---

## 8. Relationship to other suites

| Concern | Best home |
|---------|-----------|
| `needs_*` flags only | planning |
| SQL text / execution | sql |
| Policy numbers | kg |
| Vega-Lite shape | chart |
| Path tables | graph |
| **Both LLM steps + ST + infra** | **integration** |

---

## 9. Review checklist

- [ ] Only suite with full ST coverage
- [ ] Fidelity sub-area = step 2 isolation (overlaps kg/graph fixtures)
- [ ] Infra cases separated from semantic cases
- [ ] Replan limitation documented
- [ ] E2E invariants INV-SQL-TABLE / INV-POLICY-SOURCES documented for `e2e_*`
- [ ] `empty_sql_replan` requires SQL text change + second query rows when not `soft_replan`

## Related documents

- All suite docs — integration composes them
- [SHARED_RUBRICS.md](SHARED_RUBRICS.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
