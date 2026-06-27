# KG Retrieval & Source Grounding — Test Specification

> **Status:** Review only — no `kg/cases.json` or runner yet.  
> **Suite folder (planned):** `test/kg/`  
> **Layers:** `pipeline`, `graph_only`, `answer` (fixtures)  
> **Functions:** `get_graph_evidence()` / Neo4j · `answer_from_evidence()` (answer layer only)

**Note:** No Chroma/embeddings. “RAG” here = Neo4j topic search + optional SQLite `policies` table.

---

## 0. Scope

| In scope | Out of scope |
|----------|--------------|
| Exact policy numbers from indexed data | Multi-hop student paths → [graph.md](graph.md) |
| Source labels (`source_doc`) | SQL aggregation → [sql.md](sql.md) |
| Multi-policy synthesis | Chart specs → [chart.md](chart.md) |
| Negative retrieval (not found) | Routing flags → [planning.md](planning.md) |
| Conflict traps (exact vs generic) | |

Focus: **“What does the policy say?”** — not **“What path applies to student X?”**

---

## 1. Goal

Verify retrieved policy facts match seed data (`policies.csv`, `policy_rules.csv`, Neo4j) and that answers **do not hallucinate** thresholds or documents.

---

## 2. Does this suite evaluate the LLM?

**Depends on layer.**

| Layer | LLM? | What is scored |
|-------|:----:|----------------|
| **`graph_only`** | **No** | `get_graph_evidence()` → `sources`, topic matches, numeric facts in graph payload |
| **`pipeline`** | **Step 1 + 2** | Full agent: plan → graph retrieval → **`answer_from_evidence()`** prose + sources |
| **`answer`** | **Step 2 only** | Frozen `graph_context` fixture → **`answer_from_evidence()`** only |

```text
get_graph_evidence()     NO LLM    Neo4j retrieval (deterministic)
answer_from_evidence()     YES       Answer text, must_include / must_not_include
plan_question()            YES*      Only when layer=pipeline (* step 1, not content focus)
```

**Recommendation:**

- **`graph_only`** — CI without LM Studio; tests retrieval + sources.
- **`answer`** — isolate LLM step 2 for policy fidelity (like planning isolates step 1).
- **`pipeline`** — periodic E2E for KG questions.

---

## 3. How techniques relate to test cases

| Technique | Applied? | Role in kg/ |
|-----------|:--------:|-------------|
| **DT** | Yes | Policy topic → expected source + numeric fact |
| **EP** | Yes | Single / multi / negative / paraphrase classes |
| **BR** | Yes | Exact thresholds 70, 75, 85, 500 |
| **EX** | Yes | Paraphrase, GPA wording, negative doc |
| **ER** | Yes | Neo4j down, empty search |
| **ST** | **No** | → [integration.md](integration.md) |

---

## 4. Master traceability table

| Case ID | Tech | DT topic | EP partition | Layer | LLM? | Primary assertion |
|---------|:----:|:--------:|:------------:|:-----:|:----:|-------------------|
| `attendance_followup` | DT, EP, BR | TOP-ATTEND | EP-SINGLE-POLICY | pipeline / answer | answer/pipeline | **75**; not “3 absences” |
| `scholarship_thresholds` | DT, EP, BR | TOP-SCHOLAR | EP-SCHOLARSHIP | pipeline / answer | answer/pipeline | **85** + **85%** attendance |
| `financial_hold` | DT, EP, BR | TOP-FIN | EP-SINGLE-POLICY | pipeline / graph_only | graph_only: no | **500** |
| `academic_risk_score` | BR | TOP-RISK | — | graph_only | **No** | **70** in policy context |
| `advisor_duties` | DT, EP | TOP-MULTI | EP-MULTI-DOC | pipeline | step 2 | Multiple `policies` sources |
| `missing_policy` | EP, EX | TOP-NEG | EP-NEGATIVE | pipeline / graph_only | pipeline step 2 | Not found; no drone rules |
| `paraphrased_policy` | EX | TOP-ATTEND | — | answer | step 2 only | Same 75% from fixture |
| `gpa_wording` | EX | TOP-SCHOLAR | — | answer | step 2 only | Maps to avg_score 85 |
| `neo4j_unavailable` | ER | — | — | pipeline | step 2 | Warning; no fabricated policy |
| `empty_graph_search` | ER | — | — | graph_only | **No** | Empty matches |

---

## 5. Decision table (DT) — topic to cases

| Topic | Expected fact / behavior | Cases |
|-------|-------------------------|-------|
| **TOP-ATTEND** | Advisor follow-up at **75%** | `attendance_followup`, `paraphrased_policy` |
| **TOP-SCHOLAR** | avg_score ≥ **85**, attendance ≥ **85%** | `scholarship_thresholds`, `gpa_wording` |
| **TOP-FIN** | Balance hold at **500** | `financial_hold` |
| **TOP-RISK** | Academic risk avg_score **70** | `academic_risk_score` |
| **TOP-MULTI** | Multiple policy docs cited | `advisor_duties` |
| **TOP-NEG** | Policy not in index | `missing_policy` |

---

## 6. Equivalence partitions (EP)

| EP ID | Class | Case |
|-------|-------|------|
| EP-SINGLE-POLICY | One policy, numeric fact | `attendance_followup`, `financial_hold` |
| EP-SCHOLARSHIP | Scholarship thresholds | `scholarship_thresholds` |
| EP-MULTI-DOC | Multi-policy synthesis | `advisor_duties` |
| EP-NEGATIVE | Not found | `missing_policy` |
| EP-CONFLICT | Exact vs generic guess | `attendance_followup` (must_not_include) |

---

## 7. Case catalog

### 7.1 Core

| ID | Layer | Prompt | must_include | must_not_include | expected_sources |
|----|-------|--------|--------------|------------------|------------------|
| `scholarship_thresholds` | pipeline / answer | What is the minimum avg_score for scholarship support, and what if a student falls below it? | `85` | vague GPA only | `policies` |
| `attendance_followup` | pipeline / answer | What exact attendance percentage requires advisor follow-up? | `75` | `3 absences`, `three classes` | `policies` |
| `financial_hold` | graph_only / pipeline | What balance triggers the financial hold policy? | `500` | | `policies` |
| `advisor_duties` | pipeline | Summarize advisor responsibilities for at-risk students from policy documents. | advisor/intervention | | `policies` (≥2) |
| `missing_policy` | pipeline / graph_only | What is the university drone usage policy on campus? | not-found phrase | invented drone rules | none |

### 7.2 Answer layer (fixtures)

| ID | Fixture | LLM | Checks |
|----|---------|:---:|--------|
| `fidelity_exact_threshold` | `attendance_policy_graph.json` | step 2 | Exact **75** |

---

## 8. Techniques summary matrix

| Technique | Applied? | # Cases | LLM? |
|-----------|:--------:|:-------:|:----:|
| DT | Yes | 6 topics | pipeline/answer |
| EP | Yes | 5 | pipeline |
| BR | Yes | 5 | graph_only avoids LLM for numbers |
| EX | Yes | 3 | answer layer |
| ER | Yes | 2 | mixed |
| ST | **No** | 0 | integration |

---

## 9. Coverage gaps

- SQL read of `policies` table vs graph-only — define in case metadata if both allowed for `graph_only` layer.
- Source in answer **text** vs `sources` array only — pick one for v1 pass criteria.

---

## 10. Review checklist

- [ ] BR values match `policies.csv` / `policy_rules.csv`
- [ ] `graph_only` layer for CI without LM Studio
- [ ] `answer` layer for step-2-only fidelity
- [ ] ST deferred to integration

## Related documents

- [graph.md](graph.md) — paths vs policy prose
- [integration.md](integration.md) — E2E + ST
- [SHARED_RUBRICS.md](SHARED_RUBRICS.md)
