# Planning & Decomposition — Test Specification

> **Status:** `planning/cases.json` and `planning/run_eval.py` implemented.  
> **Decisions:** Option B (artifact normalization); strict R2 (F/T/F for policy-only).
> **Suite folder:** `test/planning/`  
> **Layer:** `plan`  
> **Function:** `plan_question()` (LLM step 1)

## 0. Scope

This suite tests **semantic routing only**:

- `needs_sql` — whether to read SQLite.
- `needs_graph` — whether to read Neo4j KG.
- `needs_chart` — whether to produce a Vega-Lite chart (which implies `needs_sql=true`).

**Out of scope** for this suite (covered in SQL / integration suites):

- Exact SQL text (table names, join structure).
- SQL safety and execution.
- LM Studio / network failures.
- Multi-step replanning state.

---

## 1. Goal

Verify the planner routes questions to the correct evidence channels:

| Flag | Routes to |
|------|-----------|
| `needs_sql` | SQLite |
| `needs_graph` | Neo4j KG |
| `needs_chart` | Vega-Lite chart |

The planner may also return `sql` / `graph_query`, but this suite asserts only that they are **present / empty consistent with flags**, not their detailed content.

> **Workflow note:** Downstream code runs SQL only when `needs_sql=true` and graph only when `needs_graph=true`, regardless of whether fallback text remains in the plan object. See [§8 implementation note](#8-pass--fail-criteria-all-cases).

---

## 2. How techniques relate to test cases

Planning tests one function with **three boolean outputs**. Each testing technique is a different way to choose and organize cases:

```text
Testing technique          What it defines                 Becomes in cases.json
────────────────────────────────────────────────────────────────────────────────
Decision table (DT)    →   Rule: IF signals THEN flags     → expected.needs_*
Equivalence partition (EP) → One case per question class   → one prompt per partition
Exceptional (EX)       →   Odd / ambiguous inputs          → edge-case prompts
Error (ER)             →   Planner misrouting              → "should fail" cases
Boundary / range (BR)  →   Numeric edges                   → NOT USED in planning
State change (ST)      →   Mode / replan transitions       → NOT USED in planning
```

BR and ST belong in SQL / KG / integration suites — the planner has no numeric thresholds and no session state between calls.

**Read order:**

1. [Master traceability table](#3-master-traceability-table)
2. [Decision table](#4-decision-table-dt--rules-to-cases)
3. [Equivalence partitions](#5-equivalence-partitions-ep--classes-to-cases)
4. [Case catalog](#6-case-catalog)
5. [Coverage gaps](#9-coverage-gaps)

---

## 3. Master traceability table

Each row is **one test case**.

| Case ID | Tech | DT rule | EP partition | Input condition (summary) | Expected flags (S/G/C) | Primary assertion |
|---------|:----:|:-------:|:------------:|---------------------------|:----------------------:|-------------------|
| `sql_only_enrollment` | DT, EP | R1 | EP-SQL-ENROLL | Enrollment list for C101 | T / F / F | SQL needed; graph/chart off |
| `sql_only_risk` | DT, EP | R1 | EP-SQL-RISK | Risk metrics, no policy words | T / F / F | SQL needed; no graph |
| `sql_only_named_student` | DT, EP | R1 | EP-SQL-NAMED | Named student, metrics only | T / F / F | SQL only; graph off |
| `sql_only_fee_balance` | DT, EP | R1 | EP-SQL-FEE | Fee ranking only | T / F / F | SQL only |
| `kg_only_policy` | DT, EP | R2 | EP-KG-POLICY | Policy explanation (attendance), no metrics | F / T / F | KG only |
| `graph_only_path` | DT, EP | R2 | EP-GRAPH-PATH | Path for topic, no student name | F / T / F | KG only |
| `combined_risk_intervention` | DT, EP | R5 | EP-HYBRID | Metrics + interventions | T / T / F | SQL + KG |
| `hybrid_noah_path` | DT | R3 | — | Named student + risk/path | T / T / F | SQL + KG |
| `hybrid_carlos_balance` | DT | R3 | — | Ranking SQL + named KG | T / T / F | SQL + KG |
| `plan_scholarship` | DT, EP | R5 | EP-SCHOLARSHIP | Scholarship + policy terms | T / T / F | SQL + KG |
| `plan_course_weak` | DT, EP | R5 | EP-COURSE | Course SQL + “explain weak areas” | T / T / F | SQL + KG |
| `chart_routing` | DT, EP | R4 | EP-CHART | Explicit chart + trend | T / F / T | SQL + chart |
| `chart_plus_policy` | DT | R6 | — | Chart + policy explain | T / T / T | SQL + KG + chart |
| `ambiguous_graph_word` | EP, EX | R4 | EP-AMBIG-GRAPH | “graph” = visualization, not KG | T / F / T | Chart yes; KG no |
| `explicit_table_only` | EX | R1 | — | “table only, no chart” | T / F / F | `needs_chart=false` |
| `empty_question` | EX | R7 | — | Empty string | F / F / F | All flags false; no plan artifacts |
| `off_topic` | EX | R7 | — | Weather question | F / F / F | All flags false; no plan artifacts |
| `multi_intent` | EX | R6 | — | SQL + chart + policy in one prompt | T / T / T | All three intents reflected |
| `no_tools_policy_explain` | EX | R8 | EP-NO-TOOLS | “Explain policy, do NOT query any data sources” | F / F / F | Planner respects “no tools” |
| `all_flags_false_real_question` | ER | — | — | Valid question, LLM returns all flags false | — | Evaluator marks fail |

**Legend:** S/G/C = `needs_sql` / `needs_graph` / `needs_chart`  
**Tech:** DT = decision table · EP = equivalence partition · EX = exceptional · ER = error

---

## 4. Decision table (DT) — rules to cases

This is the logical routing table.

| Rule | IF question contains… | needs_sql | needs_graph | needs_chart | Test case(s) |
|------|----------------------|:---------:|:-----------:|:-----------:|--------------|
| **R1** | list / count / metrics / enrollment, no policy | T | F | F | `sql_only_enrollment`, `sql_only_risk`, `sql_only_named_student`, `explicit_table_only` |
| **R2** | explain policy / thresholds / “what does the policy say” only | F | T | F | `kg_only_policy`, `graph_only_path` |
| **R3** | `{StudentName}` + policy/path/intervention | T | T | F | `hybrid_noah_path`, `hybrid_carlos_balance` |
| **R4** | chart / trend / plot / visualize (no explicit “no chart”) | T | F | T | `chart_routing`, `ambiguous_graph_word` |
| **R5** | metrics + intervention/policy recommendation | T | T | F | `combined_risk_intervention`, `plan_scholarship`, `plan_course_weak` |
| **R6** | chart + policy together | T | T | T | `chart_plus_policy`, `multi_intent` |
| **R7** | empty or clearly off-topic | F | F | F | `empty_question`, `off_topic` |
| **R8** | explicit instruction “do NOT query data sources / tools” | F | F | F | `no_tools_policy_explain` |

**Canonical preference for policy text:**  
For rules **R2, R3, R5, R6** we prefer `needs_graph=true` for policy explanations, even if policy text also exists in SQLite views. This suite does **not** accept `needs_sql=true` alone as a substitute for graph routing on policy-explanation prompts.

---

## 5. Equivalence partitions (EP) — classes to cases

Each partition is one “class of question” with similar routing behavior.

| EP ID | Question class | Representative case | Why one case is enough |
|-------|----------------|---------------------|------------------------|
| EP-SQL-RISK | Risk view query | `sql_only_risk` | All risk-list questions → SQL-only |
| EP-SQL-ENROLL | Enrollment list | `sql_only_enrollment` | Distinct shape from risk view |
| EP-SQL-NAMED | Named student metrics only | `sql_only_named_student` | Graph stays off without policy wording |
| EP-SQL-FEE | Fee/balance ranking | `sql_only_fee_balance` | Different metric focus |
| EP-KG-POLICY | Policy prose only | `kg_only_policy` | Policy explanation without metrics |
| EP-GRAPH-PATH | Topic → policy → intervention path | `graph_only_path` | Path reasoning without a specific student |
| EP-HYBRID | Metrics + interventions | `combined_risk_intervention` | Combined routing |
| EP-CHART | Chart or trend requested | `chart_routing` | Chart flag on |
| EP-AMBIG-GRAPH | “graph” ambiguity | `ambiguous_graph_word` | “graph” = chart, not Neo4j |
| EP-SCHOLARSHIP | Scholarship + policy | `plan_scholarship` | Domain-specific hybrid |
| EP-COURSE | Course analytics + explanation | `plan_course_weak` | Course view + KG |
| EP-NO-TOOLS | Explicit “no tools” | `no_tools_policy_explain` | Instruction overrides normal routing |

**EP completeness:** 12 partitions → 12 representative cases (some also satisfy DT rules).

---

## 6. Case catalog

These become entries in `planning/cases.json`.  
Fields `techniques`, `dt_rule`, and `ep_partition` are recommended metadata.

### 6.1 Core routing (DT + EP)

| ID | Tech | Prompt | Flags S/G/C | Core checks |
|----|------|--------|:-----------:|-------------|
| `sql_only_enrollment` | DT R1, EP-SQL-ENROLL | List all students enrolled in C101. | T/F/F | `needs_sql=true`, others false |
| `sql_only_risk` | DT R1, EP-SQL-RISK | Which students are at high risk? | T/F/F | As above |
| `sql_only_named_student` | DT R1, EP-SQL-NAMED | What is Noah Patel's avg_score and balance_due? | T/F/F | Named filter implied; KG stays off |
| `kg_only_policy` | DT R2, EP-KG-POLICY | Explain the attendance policy when a student misses too many classes. | F/T/F | `needs_graph=true`, `needs_sql=false` |
| `graph_only_path` | DT R2, EP-GRAPH-PATH | What policy and intervention path applies to irregular attendance? | F/T/F | Path reasoning in KG only |
| `combined_risk_intervention` | DT R5, EP-HYBRID | Which students are at risk based on avg_score and what interventions do policy documents recommend? | T/T/F | SQL + KG both needed |
| `chart_routing` | DT R4, EP-CHART | Create a chart of attendance trend by month for at-risk students. | T/F/T | `needs_chart=true` and `needs_sql=true` |

### 6.2 Extended routing (DT / EP)

| ID | Tech | Prompt | Flags S/G/C |
|----|------|--------|:-----------:|
| `hybrid_noah_path` | DT R3 | What risk factors are linked to Noah Patel, and which policy and intervention path applies to irregular attendance? | T/T/F |
| `hybrid_carlos_balance` | DT R3 | Which high-risk students have the largest fee balances, and what intervention paths does the knowledge graph recommend for Carlos Reyes? | T/T/F |
| `plan_scholarship` | EP-SCHOLARSHIP | Who qualifies for scholarship support based on avg_score, attendance, and fee status? | T/T/F |
| `plan_course_weak` | EP-COURSE | Show average grade by course and explain weak areas. | T/T/F |
| `sql_only_fee_balance` | EP-SQL-FEE | Show students ordered by largest balance_due. | T/F/F |
| `chart_plus_policy` | DT R6 | Chart at-risk attendance by month and summarize the intervention policy. | T/T/T |

### 6.3 Exceptional (EX)

| ID | Tech | Prompt | Flags S/G/C | Checks |
|----|------|--------|:-----------:|--------|
| `ambiguous_graph_word` | EP-AMBIG, EX | Show a graph of monthly attendance for at-risk students. | T/F/T | `needs_graph=false` even though “graph” is mentioned |
| `explicit_table_only` | EX | List at-risk students as a table only, no chart. | T/F/F | `needs_chart=false` despite chartable data |
| `empty_question` | EX, R7 | `""` (empty string) | F/F/F | No flags; no meaningful plan artifacts |
| `off_topic` | EX, R7 | What is the weather in Boston today? | F/F/F | Planner does not route to student DB/KG |
| `multi_intent` | EX, R6 | List at-risk students and chart fee balances and explain scholarship policy. | T/T/T | SQL + chart + policy reflected in flags |
| `no_tools_policy_explain` | EX, R8 | Without querying any databases or tools, explain the attendance policy in plain language only. | F/F/F | Explicit “no tools” overrides normal R2 |

### 6.4 Error (ER) — logical misrouting

These are not separate prompts but **failure patterns** the evaluator checks for:

| ID | Tech | Setup / condition | Pass condition |
|----|------|-------------------|----------------|
| `all_flags_false_real_question` | ER | Any valid, in-domain question where the LLM sets all flags false | Test run marked as **failure** |

Infra errors (LM Studio down, invalid JSON, SQL safety) are handled in **integration** tests, not in this suite.

---

## 7. Planned `cases.json` fields

Example entry:

```json
{
  "id": "sql_only_risk",
  "techniques": ["DT", "EP"],
  "dt_rule": "R1",
  "ep_partition": "EP-SQL-RISK",
  "layer": "plan",
  "question": "Which students are at high risk?",
  "expected": {
    "needs_sql": true,
    "needs_graph": false,
    "needs_chart": false
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Unique test case id |
| `layer` | yes | Always `"plan"` |
| `question` | yes | Prompt string |
| `expected` | yes | Boolean flags `needs_sql`, `needs_graph`, `needs_chart` |
| `techniques` | no | e.g. `["DT","EP"]` for coverage reporting |
| `dt_rule` | no | `R1`–`R8` when applicable |
| `ep_partition` | no | EP id when applicable |

Downstream suites (SQL / KG / integration) add fields for SQL content, safety, and execution.

---

## 8. Pass / fail criteria (all cases)

### Flag match

`needs_sql`, `needs_graph`, `needs_chart` match `expected`.

### Flag consistency invariants

1. If `needs_chart=true` then `needs_sql=true` (charts require rows).
2. If `needs_sql=false` then `sql` (if present) must be empty or null.
3. If `needs_graph=false` then `graph_query` (if present) must be empty or null.

### No spurious planning artifacts

For `empty_question` and `off_topic`, planner should not invent a meaningful routing plan.

Violations of flag match or invariants are **failures**. Spurious artifacts on EX cases are **failures** for this suite.

### Implementation note (Option B — implemented)

**Decision:** Option B — `plan_question()` normalizes the merged plan so artifacts match flags.

`_normalize_plan()` in `deterministic.py`:

1. If `needs_chart=true` → force `needs_sql=true`.
2. If `needs_sql=false` → `sql=""`.
3. If `needs_graph=false` → `graph_query=""`.
4. If a flag is true but the field is empty → fill from fallback SQL / graph query.

The planning runner (`test/planning/run_eval.py`) asserts flag match **and** these invariants.

### R2 strict routing (approved)

**Decision:** **Strict F/T/F** for policy-only prompts (rules R2). No alternate pass via `needs_sql=true` on the `policies` table.

The planner prompt instructs: policy explanations without metrics → `needs_graph=true`, `needs_sql=false`, `sql=""`.

Cases: `kg_only_policy`, `graph_only_path`.

---

## 9. Coverage gaps

| Gap / scenario | Technique | Planned case? | Action |
|----------------|-----------|---------------|--------|
| F / T / T (graph + chart, no SQL) | DT | None | Invalid for this agent; skip |
| F / F / T (chart without SQL) | DT | None | Invalid; chart requires SQL |
| Numeric thresholds (70/75/85/500) | BR | None | Covered in SQL / KG suites |
| Replan after bad plan | ST | None | Covered in integration tests |
| `no_tools_policy_explain` honored by LLM | EX | Yes | May fail until prompt/planner tuned — track as aspirational |

---

## 10. Review checklist

- [ ] Every DT rule **R1–R8** mapped to ≥ 1 case
- [ ] Every EP partition mapped to ≥ 1 case
- [ ] EX cases cover ambiguity, negative instructions, off-topic, and multi-intent
- [ ] SQL / KG details and infra errors stay out of this planning suite
- [ ] `cases.json` schema includes `expected.needs_*` for every case
- [ ] Option B invariant normalization verified in code
- [ ] Strict R2 (F/T/F) approved — no SQL alternate for policy-only cases

## Related documents

- [SHARED_RUBRICS.md](SHARED_RUBRICS.md) — technique legend
- [ARCHITECTURE.md](ARCHITECTURE.md) — planner merge and workflow
- [sql.md](sql.md) — SQL content and execution (downstream)
