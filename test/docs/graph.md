# Graph Relationship Paths — Test Specification

> **Status:** Review only — no `graph/cases.json` or runner yet.  
> **Suite folder (planned):** `test/graph/`  
> **Layers:** `graph_only`, `pipeline`, `answer` (fixtures)  
> **Functions:** `get_graph_evidence()` · `graph_artifact_from_context()` · `answer_from_evidence()` (optional)

---

## 0. Scope

Focus: **“What path applies to this student / topic?”** — not policy prose thresholds ([kg.md](kg.md)).

| In scope | Out of scope |
|----------|--------------|
| Student → risk → policy → intervention paths | Exact 75/85/500 facts → kg |
| `graph_artifact` tables | SQL aggregations → sql |
| `sources_must_contain` / seed path tuples | Chart specs → chart |
| Path count (1 vs 2) | Plan routing → planning |

---

## 1. Goal

Verify Neo4j multi-hop paths match seed CSV graph and appear correctly in **graph evidence artifacts** (and optionally answer text).

---

## 2. Does this suite evaluate the LLM?

**Mostly no — retrieval is deterministic.**

| Layer | LLM? | Scored |
|-------|:----:|--------|
| **`graph_only`** | **No** | `get_graph_evidence()` + `graph_artifact_from_context()` — paths, sources, markdown tables |
| **`pipeline`** | **Step 2 optional** | If asserting `answer` text paths, uses `answer_from_evidence()` |
| **`answer`** | **Step 2 only** | Frozen `graph_context` → path strings in prose |

```text
get_graph_evidence()           NO LLM    Primary graph suite target
graph_artifact_from_context()  NO LLM    Table structure + path rows
plan_question()                YES*      * pipeline only, not graph content
answer_from_evidence()         YES       Optional — path wording in answer
```

**Recommendation:** v1 **`graph_only`** for CI; add **`answer`** layer only if prose path formatting must be LLM-tested.

---

## 3. How techniques relate to test cases

| Technique | Applied? | Role |
|-----------|:--------:|------|
| **DT** | Yes | Query shape → path type (named single/multi/topic/generic) |
| **EP** | Yes | 5 path query classes |
| **BR** | Yes | Path **count** (1 vs 2), not numeric thresholds |
| **EX** | Yes | Unknown student, low-risk empty graph |
| **ER** | Yes | Neo4j unavailable |
| **ST** | **No** | integration |

---

## 4. Master traceability table

| Case ID | Tech | DT shape | EP partition | Layer | LLM? | Primary assertion |
|---------|:----:|:--------:|:------------:|:-----:|:----:|-------------------|
| `noah_irregular_attendance` | DT, EP, BR | SHAPE-1-PATH | EP-NAMED-SINGLE | graph_only / pipeline | optional step 2 | `expected_paths_exact: 1`; path content matches seed |
| `carlos_intervention_paths` | DT, EP, BR | SHAPE-2-PATH | EP-NAMED-MULTI | graph_only / answer | optional step 2 | `expected_paths_exact: 2`; fail if ≠2 |
| `owen_risk_factors` | EP | SHAPE-NAMED | EP-NAMED-RISK-LIST | graph_only | **No** | ≥1 complete path |
| `topic_irregular_attendance` | EP | SHAPE-TOPIC | EP-TOPIC-STUDENTS | graph_only | **No** | Noah, Carlos, Owen |
| `path_irregular_attendance_generic` | DT, EP | SHAPE-GENERIC | EP-PATH-NO-STUDENT | graph_only | **No** | Path without student name |
| `unknown_student` | EX | — | — | graph_only | **No** | Empty artifact; zero fabricated path/risk rows |
| `student_no_graph_data` | EX | — | — | graph_only | **No** | Maya Tran minimal/empty |
| `neo4j_down` | ER | — | — | pipeline | step 2 if answer | warning in graph_context |

---

## 5. Decision table (DT) — query shape

| Shape | IF question… | Expected evidence | Case(s) |
|-------|--------------|-------------------|---------|
| **SHAPE-1-PATH** | Named student + specific risk topic | 1 path row | `noah_irregular_attendance` |
| **SHAPE-2-PATH** | Named student, all paths | 2 path rows | `carlos_intervention_paths` |
| **SHAPE-NAMED** | Named student, path required | ≥1 path | `owen_risk_factors` |
| **SHAPE-TOPIC** | Which students have risk factor X | student list | `topic_irregular_attendance` |
| **SHAPE-GENERIC** | Policy path for topic, no student | path without student_name focus | `path_irregular_attendance_generic` |

---

## 6. Equivalence partitions (EP)

| EP ID | Case |
|-------|------|
| EP-NAMED-SINGLE-PATH | `noah_irregular_attendance` |
| EP-NAMED-MULTI-PATH | `carlos_intervention_paths` |
| EP-NAMED-RISK-LIST | `owen_risk_factors` |
| EP-TOPIC-STUDENTS | `topic_irregular_attendance` |
| EP-PATH-NO-STUDENT | `path_irregular_attendance_generic` |

---

## 7. Graph artifact checks (no LLM)

### 7.1 Table structure

When evidence exists:

- **Risk table** columns: `student_name`, `risk_factor`, `evidence_text`
- **Paths table** columns: `student_name`, `risk_factor`, `policy`, `intervention`
- `graph_artifact.markdown` non-empty

When evidence does **not** exist (see §7.3): markdown empty or explicit “none found” wording from formatter — **no fabricated rows**.

### 7.2 Boundary — exact path count (BR)

For named-student path cases, the checker compares `len(path_rows)` to **`expected_paths_exact`**:

| Case | `expected_paths_exact` | Fail if |
|------|------------------------|---------|
| `noah_irregular_attendance` | **1** | 0 paths (under-connected) or ≥2 (over-connected / duplicate hops) |
| `carlos_intervention_paths` | **2** | ≠2 (drops a path or merges extras) |

Count source: `graph_artifact.path_rows` or `graph_context.students[].policy_paths.paths` after dedupe by `(student_name, risk_factor, policy, intervention)`.

#### Seed CSV ground truth (required for BR cases)

Path rows must match the **seed graph chain**, not merely contain plausible strings. This prevents passing when Neo4j is over-connected (extra hops, wrong policy, or duplicate paths).

**CSV chain:** `student_risk_factors.csv` → `risk_policy_links.csv` → `policies.csv` → `policy_intervention_links.csv` → `interventions.csv`

| Student | student_id | Expected path tuples `(risk_factor, policy_name, intervention_name)` | CSV IDs |
|---------|------------|------------------------------------------------------------------------|---------|
| **Noah Patel** | S002 | **1 row only:** `(Irregular Attendance, Attendance Intervention Policy, Weekly Lab Attendance)` | RF→P002→I001 |
| **Carlos Reyes** | S008 | **2 rows exactly:** `(Balance Due Greater Than 500, Financial Hold Policy, Financial Aid Review)` **and** `(Irregular Attendance, Attendance Intervention Policy, Weekly Lab Attendance)` | P004→I002; P002→I001 |

Checker (v1 — display names in artifact):

1. `expected_paths_exact` count matches.
2. **`expected_path_rows`** in `cases.json` is a **required set** of tuples; every tuple must appear in actual path rows (order irrelevant).
3. **Fail** if any extra path row exists for that student (over-connected graph).
4. Optional strict mode: also verify `source_doc` on each hop (`student_risk_factors` vs `policies`) — defer to v2.

Example `expected_path_rows` for Noah:

```json
"expected_path_rows": [
  {
    "student_name": "Noah Patel",
    "risk_factor": "Irregular Attendance",
    "policy": "Attendance Intervention Policy",
    "intervention": "Weekly Lab Attendance"
  }
]
```

Example for Carlos (both rows required):

```json
"expected_path_rows": [
  {
    "student_name": "Carlos Reyes",
    "risk_factor": "Balance Due Greater Than 500",
    "policy": "Financial Hold Policy",
    "intervention": "Financial Aid Review"
  },
  {
    "student_name": "Carlos Reyes",
    "risk_factor": "Irregular Attendance",
    "policy": "Attendance Intervention Policy",
    "intervention": "Weekly Lab Attendance"
  }
]
```

**ID reference (for maintainers / future strict mode):**

| risk_factor | policy_id | policy_name | intervention_id | intervention_name |
|-------------|-----------|-------------|-----------------|-------------------|
| Irregular Attendance | P002 | Attendance Intervention Policy | I001 | Weekly Lab Attendance |
| Balance Due Greater Than 500 | P004 | Financial Hold Policy | I002 | Financial Aid Review |

Supplementary `must_include` strings (optional, weaker than tuple check):

| Case | `must_include` |
|------|----------------|
| `noah_irregular_attendance` | Irregular Attendance, Attendance Intervention Policy, Weekly Lab Attendance |
| `carlos_intervention_paths` | Financial Hold Policy, Financial Aid Review, Attendance Intervention Policy, Weekly Lab Attendance |

### 7.3 Exceptional — `unknown_student` semantics

Prompt: *What intervention paths apply to Jane Doe?* (name not in seed data)

**Pass when all of:**

1. No student block for Jane Doe in `graph_context.students`, **or** block exists with empty `risk_factors` and empty `paths`.
2. `graph_artifact.path_rows` length **0** and `graph_artifact.risk_rows` length **0** (or artifact markdown empty).
3. **No fabricated** `risk_factor`, `policy`, or `intervention` strings in artifact rows.
4. Optional pipeline layer: answer states student not found / no graph evidence — must **not** invent a path.

**Fail when:** any path or risk row names Jane Doe with made-up policy/intervention content.

Same rules apply to `student_no_graph_data` (Maya Tran — minimal/low-risk seed): empty or minimal paths OK; fabrication is not.

### 7.4 Source labels — how checking works

Do **not** use a bare `expected_sources` field without defining semantics. Use one of the patterns below.

#### Pattern A — `sources_must_contain` (default for graph suite)

**Meaning:** **All** listed labels must appear in `actual_sources`. This is **not** “at least one of”.

```json
"sources_must_contain": ["policies", "student_risk_factors"]
```

```text
FAIL if ∃ label ∈ sources_must_contain such that label ∉ actual_sources
PASS iff sources_must_contain ⊆ actual_sources
```

Use for `noah_irregular_attendance` and `carlos_intervention_paths` because both student risk evidence and policy hops should appear.

#### Pattern B — `sources_any_of` (“at least one of”)

**Meaning:** pass if **any** listed label appears. Use sparingly (e.g. generic topic path where either policies or student_risk_factors may surface first).

```json
"sources_any_of": ["policies", "student_risk_factors"]
```

```text
PASS if sources_any_of ∩ actual_sources ≠ ∅
FAIL if no overlap
```

Do **not** use Pattern B for Noah/Carlos BR cases — that would pass with only one source and miss incomplete retrieval.

#### Pattern C — `sources_may_contain`

**Informational allow-list** only. Never used alone to pass/fail. Extra labels in `actual_sources` not listed here are still OK.

#### Combined example

```json
{
  "sources_must_contain": ["policies", "student_risk_factors"],
  "sources_may_contain": ["advising_notes"],
  "sources_any_of": []
}
```

| Case type | Recommended pattern |
|-----------|---------------------|
| Named student + paths (Noah, Carlos) | Pattern A: both required |
| Policy path only, no student RF rows | `sources_must_contain: ["policies"]` |
| Unknown / empty graph | `sources_must_contain: []` |
| Loose topic search (if ever needed) | Pattern B `sources_any_of` |

**Deprecated:** `expected_sources` without `_must_contain` / `_any_of` — avoid in new `cases.json`.

---

## 8. Planned `cases.json` fields (graph)

```json
{
  "id": "noah_irregular_attendance",
  "techniques": ["DT", "EP", "BR"],
  "dt_shape": "SHAPE-1-PATH",
  "ep_partition": "EP-NAMED-SINGLE",
  "layer": "graph_only",
  "question": "What risk factors are linked to Noah Patel, and which policy and intervention path applies to irregular attendance?",
  "expected_paths_exact": 1,
  "expected_path_rows": [
    {
      "student_name": "Noah Patel",
      "risk_factor": "Irregular Attendance",
      "policy": "Attendance Intervention Policy",
      "intervention": "Weekly Lab Attendance"
    }
  ],
  "must_include": [
    "Irregular Attendance",
    "Attendance Intervention Policy",
    "Weekly Lab Attendance"
  ],
  "sources_must_contain": ["policies", "student_risk_factors"],
  "sources_may_contain": []
}
```

```json
{
  "id": "carlos_intervention_paths",
  "expected_paths_exact": 2,
  "expected_path_rows": [
    {
      "student_name": "Carlos Reyes",
      "risk_factor": "Balance Due Greater Than 500",
      "policy": "Financial Hold Policy",
      "intervention": "Financial Aid Review"
    },
    {
      "student_name": "Carlos Reyes",
      "risk_factor": "Irregular Attendance",
      "policy": "Attendance Intervention Policy",
      "intervention": "Weekly Lab Attendance"
    }
  ],
  "sources_must_contain": ["policies", "student_risk_factors"]
}
```

```json
{
  "id": "unknown_student",
  "layer": "graph_only",
  "question": "What intervention paths does the knowledge graph recommend for Jane Doe?",
  "expected_paths_exact": 0,
  "expected_risk_rows_exact": 0,
  "sources_must_contain": [],
  "must_not_include": ["Jane Doe", "Financial Aid Review", "Weekly Lab Attendance"]
}
```

Note: `must_not_include` for `unknown_student` applies to **artifact row content**, not the question text. Use separate answer-layer checks if testing prose.

---

## 9. Techniques summary matrix

| Technique | Applied? | # Cases | LLM? |
|-----------|:--------:|:-------:|:----:|
| DT | Yes | 5 shapes | **No** (graph_only) |
| EP | Yes | 5 | **No** |
| BR | Yes | 2 (path count) | **No** |
| EX | Yes | 2 | **No** |
| ER | Yes | 1 | pipeline optional |
| ST | **No** | 0 | integration |

---

## 10. Open questions

1. Pass on **graph_artifact** only vs require path strings in **answer** text?
2. Cypher-level tests manual in Neo4j Browser?
3. v2: assert CSV **IDs** (P002, I001) in Neo4j node properties in addition to display names?

---

## 11. Review checklist

- [ ] v1 = `graph_only` without LM Studio
- [ ] kg vs graph split clear
- [ ] BR: `expected_paths_exact` + **`expected_path_rows`** match seed CSVs for Noah/Carlos
- [ ] Extra path rows for same student fail (over-connected graph)
- [ ] `unknown_student` empty artifact + no fabrication documented
- [ ] Source checking uses `sources_must_contain` (all required), not “at least one of”, for BR cases

## Related documents

- [kg.md](kg.md) — policy facts
- [integration.md](integration.md) — hybrid E2E
- [SHARED_RUBRICS.md](SHARED_RUBRICS.md)
