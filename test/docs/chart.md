# Chart vs Table Decision — Test Specification

> **Status:** Review only — no `chart/cases.json` or runner yet.  
> **Suite folder (planned):** `test/chart/`  
> **Layers:** `artifact_only`, `pipeline`, `answer` (fixtures)  
> **Functions:** `plan_question()` · `generate_table_or_chart_spec()` · `answer_from_evidence()` (answer layer)

---

## 0. Scope

| In scope | Out of scope |
|----------|--------------|
| `needs_chart` + `artifact.type` | Neo4j paths → [graph.md](graph.md) |
| Vega-Lite structure | Policy numbers → [kg.md](kg.md) |
| Chart vs table intent | SQL fragment details → [sql.md](sql.md) |
| “graph” = chart disambiguation | Full E2E → [integration.md](integration.md) |

---

## 1. Goal

Verify visualization **routing** (chart vs table) and **deterministic** Vega-Lite artifact shape.

---

## 2. Does this suite evaluate the LLM?

**Mixed — mostly deterministic artifact; LLM only for routing and description.**

| Layer | LLM? | Scored |
|-------|:----:|--------|
| **`artifact_only`** | **No** | Fixed SQL rows + `needs_chart` flag → `generate_table_or_chart_spec()` output |
| **`pipeline`** | **Step 1** | `needs_chart` from `plan_question()`; artifact from deterministic builder |
| **`answer`** | **Step 2** | Chart **description** in prose from `answer_from_evidence()` + fixture |

```text
plan_question()              YES (step 1)   needs_chart flag only
generate_table_or_chart_spec NO             Vega-Lite JSON — main chart suite focus
answer_from_evidence()       YES (step 2)   "chart shows month vs attendance" — optional layer
```

**Most chart quality is NOT LLM-evaluated** — encoding fields are deterministic from SQL columns.

---

## 3. How techniques relate to test cases

| Technique | Applied? | Notes |
|-----------|:--------:|-------|
| **DT** | Yes | User intent → needs_chart + artifact.type + mark |
| **EP** | Yes | Time series, distribution, explicit table, keyword, ambiguous |
| **BR** | Partial | Single-point series, empty data |
| **EX** | Yes | Ambiguous “graph”, dual table+chart ask, no data |
| **ER** | Yes | Chart flag but zero SQL rows |
| **ST** | **No** | replan → integration |

---

## 4. Master traceability table

| Case ID | Tech | DT row | EP partition | Layer | LLM? | Primary assertion |
|---------|:----:|:------:|:------------:|:-----:|:----:|-------------------|
| `timeseries_attendance` | DT, EP | VIS-CHART-TS | EP-TS-ATTEND | pipeline / artifact_only | pipeline: step 1 | chart; x=month, y=attendance_pct |
| `distribution_risk_level` | DT, EP | VIS-CHART-DIST | EP-DIST-RISK | pipeline / artifact_only | pipeline: step 1 | chart; bar; risk_level counts |
| `table_course_averages` | DT, EP | VIS-TABLE | EP-TABLE-EXPLICIT | pipeline | step 1 | needs_chart=false; type=table |
| `explicit_chart_keyword` | EP | VIS-CHART-TS | EP-KEYWORD-CHART | pipeline | step 1 | Same as timeseries |
| `ambiguous_graph_word` | EP, EX | VIS-CHART-TS | EP-AMBIG-GRAPH | pipeline | step 1 | needs_chart=true; needs_graph=false |
| `chart_single_month` | BR | VIS-CHART-TS | — | artifact_only | **No** | Single-point line spec |
| `chart_no_data` | EX, ER | — | — | artifact_only | **No** | Empty data.values |
| `table_and_chart_ask` | EX | — | — | pipeline | step 1 | Expected flags TBD |
| `answer_chart_description` | — | — | — | answer | **step 2** | must_include chart, month, attendance |

---

## 5. Decision table (DT) — visualization intent

| Row | IF signal… | needs_chart | artifact.type | mark | Case(s) |
|-----|------------|:-----------:|:-------------:|------|---------|
| VIS-CHART-TS | chart/trend/month/time series | T | chart | line | `timeseries_attendance`, `ambiguous_graph_word` |
| VIS-CHART-DIST | distribution / counts per category | T | chart | bar | `distribution_risk_level` |
| VIS-TABLE | table only / list / no chart | F | table | — | `table_course_averages`, `explicit_table_only`* |

\* `explicit_table_only` lives in [planning.md](planning.md) for routing; chart suite asserts artifact.type only when run as pipeline slice.

---

## 6. Equivalence partitions (EP)

| EP ID | Case |
|-------|------|
| EP-TS-ATTEND | `timeseries_attendance` |
| EP-DIST-RISK | `distribution_risk_level` |
| EP-TABLE-EXPLICIT | `table_course_averages` |
| EP-KEYWORD-CHART | `explicit_chart_keyword` |
| EP-AMBIG-GRAPH | `ambiguous_graph_word` |

---

## 7. Vega-Lite checks (all chart cases, no LLM)

- `$schema` contains `vega-lite`
- `data.values` array (may be empty for ER)
- `mark` ∈ {`line`, `bar`}
- `encoding.x.field`, `encoding.y.field` present
- Fields exist in SQL columns

---

## 8. Techniques summary matrix

| Technique | Applied? | # Cases | LLM? |
|-----------|:--------:|:-------:|:----:|
| DT | Yes | 3 rows | step 1 only (pipeline) |
| EP | Yes | 5 | step 1 |
| BR | Partial | 1–2 | **No** (artifact_only) |
| EX | Yes | 2–3 | mixed |
| ER | Yes | 1 | **No** |
| ST | **No** | 0 | integration |

---

## 9. Open questions

1. Require `bar` for distribution — code today always uses `line`.
2. `ambiguous_graph_word` — primary owner planning vs chart (both assert different fields).
3. Answer-layer chart description — required in v1 or optional?

---

## 10. Review checklist

- [ ] `artifact_only` layer for CI (no LM Studio)
- [ ] LLM scope: step 1 flag + optional step 2 description only
- [ ] ST explicitly out of scope

## Related documents

- [planning.md](planning.md) — `needs_chart` routing
- [sql.md](sql.md) — SQL rows feeding charts
- [ARCHITECTURE.md](ARCHITECTURE.md)
