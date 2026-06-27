# Model Evaluation — Using This Suite to Compare LLMs

> **Purpose:** Explain what the test suite measures when comparing models, what it does **not** measure, and how to turn results into a practical benchmark for this student-management agent.  
> **Related:** [RUNNING_TESTS.md](../RUNNING_TESTS.md) · [HALLUCINATION_CASES.md](HALLUCINATION_CASES.md) · [TESTCASES.md](../TESTCASES.md)

The tests you’ve designed are a strong foundation for comparing LLMs, but they are not a complete story by themselves. They answer **“Does this model behave correctly in my stack?”** more than **“Is this model globally better?”**

---

## 1. What the current tests measure

If you run the same suite against different models (same prompts, same data, same infra), you already get useful, model-sensitive signals.

### Planning suite

**Measures:** How often each model sets `needs_sql` / `needs_graph` / `needs_chart` correctly.

**Good for:** Tool-routing intelligence.

**Comparison metric:** % of planning cases passed per model.

### SQL suite

**Measures (pipeline layer):**

- Schema understanding and correct view choice
- Correct filters, LIMITs, flags
- Avoiding nonexistent columns and unsafe SQL

**Good for:** “Can this model write correct, safe SQL over my schema?”

**Comparison metrics:** % of SQL pipeline cases where SQL passes the validator, executes, and rows match ground truth.  
(`sql_only` layer is deterministic — same for every model; use `pipeline` for LLM comparison.)

### KG + Graph suites

**KG (`kg/`):**

- Fidelity of policy facts (70 / 75 / 85 / 500) from graph + policies
- Non-hallucination about rules and documents

**Graph (`graph/`):**

- Primarily **non-LLM** (path retrieval correctness)
- Optional pipeline/answer layers for how well the model verbalizes paths

**Comparison metrics:** % of KG cases with correct thresholds and no hallucinated policy content.

### Integration suite

**Measures:**

- End-to-end success: full answer correct, grounded, no invented rows/policies
- Replan behavior when evidence is missing
- Behavior under infra issues (offline mode, LM down, Neo4j down)

**Comparison metrics:**

- % of e2e cases fully correct
- # of hallucination violations (answer mentions entities/policies not in evidence)
- Replan success rate (e.g. `empty_sql_replan`)

### Put simply

If Model A passes **95%** of planning + SQL + KG + integration cases and Model B passes **70%**, you already know A is much better **for this student-management agent**.

---

## 2. What these tests do not fully cover

For “which LLM is better overall”, missing dimensions include:

| Dimension | Gap |
|-----------|-----|
| **General reasoning depth** | Tests hit your specific schema/rules, not open-ended reasoning or chain-of-thought |
| **Robustness to phrasing** | Some paraphrase coverage (KG), but not large paraphrase / noisy-input sets |
| **Style / usability** | Politeness, clarity, length, explanation quality barely tested (except minimal must/must_not) |
| **Latency / cost** | Spec is functionality-centric; no response-time or token-usage comparison |
| **Domain transfer** | Tightly bound to student management; no signal for other domains without new tests |

---

## 3. How to turn this into a practical LLM benchmark

### Step 1 — Run the full suite per model

Same prompts, same data, same infra. Compare Model X vs Y vs Z.

```powershell
# Set LMSTUDIO_MODEL in .env for each model, then:
python test/run_model_eval.py
```

Results append to:

- `test/results/model_eval_history.csv` — pass/fail matrix (one column per model run)
- `test/results/model_eval_runs.csv` — aggregate counts per run

For **answer-level human review** (hallucination focus):

```powershell
python test/run_hallucination_eval.py
```

→ `test/results/hallucination_eval_answers.csv` with `review_text` and `human_verdict` columns.

### Step 2 — Compute per-layer scores

| Layer | Score |
|-------|-------|
| Planning | % cases with correct routing flags |
| SQL | % pipeline cases fully correct (validator + execution + rows) |
| KG | % cases with correct thresholds and no policy hallucination |
| Integration | % e2e cases fully correct; hallucination violation count; replan success % |

Use `model_eval_history.csv` to filter rows by `suite` and count `pass` / `fail` / `skip` per column.

### Step 3 — Define a simple weighted score

Example weighting for **this project**:

| Area | Weight |
|------|-------:|
| Planning | 20% |
| SQL | 25% |
| KG | 20% |
| Integration (e2e) | 35% |

**Final model score** = weighted average of pass rates. Use this to rank models for the student-management agent.

Adjust weights if your deployment cares more about one layer (e.g. higher SQL weight for analytics-heavy use).

### Step 4 — Add a small “style” section if you care

5–10 manually judged questions:

- Rate clarity, conciseness, helpfulness (1–5)
- Keep separate from correctness (do not mix into the weighted functional score)

The hallucination answer log (`hallucination_eval_answers.csv`) is a natural place to record these judgments in `human_verdict` / `human_notes`.

---

## 4. Minimal extensions for stronger comparison

| Extension | Benefit |
|-----------|---------|
| **Paraphrase expansions** | For selected planning/SQL/KG/integration cases, add 3–5 paraphrased prompts each → robustness to query wording |
| **Tiny generic reasoning section** | 5–10 simple non-domain tasks (math, logic, instructions) in a separate file → catch models that are “good at schema but bad at thinking” |

See [HALLUCINATION_CASES.md](HALLUCINATION_CASES.md) for the anti-hallucination registry; extend `hallucination_cases.json` as new cases are implemented.

---

## Summary

| Question | Answer |
|----------|--------|
| Good enough to compare LLMs for **this agent**? | **Yes** — planning, SQL, KG, graph, e2e |
| A global “best LLM at everything” benchmark? | **No** |
| Practical workflow | Run all suites per model → per-area pass rates → weighted score → optional paraphrase + style/reasoning checks |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-27 | Initial model evaluation guide |
