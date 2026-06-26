from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from student_rag.llm import get_llm
from student_rag.paths import DATA_DIR, DEFAULT_TERM


@dataclass(frozen=True)
class GraphFact:
    head_label: str
    head_name: str
    relation: str
    tail_label: str
    tail_name: str
    source_doc: str
    evidence_text: str
    confidence: float = 1.0
    term: str = DEFAULT_TERM

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fact(
    head_label: str,
    head_name: str,
    relation: str,
    tail_label: str,
    tail_name: str,
    source_doc: str,
    evidence_text: str,
    confidence: float = 1.0,
) -> GraphFact:
    return GraphFact(
        head_label=head_label,
        head_name=head_name,
        relation=relation,
        tail_label=tail_label,
        tail_name=tail_name,
        source_doc=source_doc,
        evidence_text=evidence_text,
        confidence=confidence,
        term=DEFAULT_TERM,
    )


def _read_csv_rows(csv_name: str, data_dir: Path | None = None) -> list[dict[str, str]]:
    data_dir = data_dir or DATA_DIR
    csv_path = data_dir / csv_name
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _student_name_map(data_dir: Path | None = None) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in _read_csv_rows("students.csv", data_dir=data_dir):
        names[row["student_id"]] = f"{row['first_name']} {row['last_name']}"
    return names


def _policy_name_map(data_dir: Path | None = None) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in _read_csv_rows("policies.csv", data_dir=data_dir):
        names[row["policy_id"]] = row["policy_name"]
    return names


def _intervention_name_map(data_dir: Path | None = None) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in _read_csv_rows("interventions.csv", data_dir=data_dir):
        names[row["intervention_id"]] = row["intervention_name"]
    return names


def build_graph_facts(data_dir: Path | None = None) -> list[GraphFact]:
    """Build graph facts from policy and advising CSV files in data/student_management."""
    data_dir = data_dir or DATA_DIR
    facts: list[GraphFact] = []
    student_names = _student_name_map(data_dir)
    policy_names = _policy_name_map(data_dir)
    intervention_names = _intervention_name_map(data_dir)

    for row in _read_csv_rows("risk_policy_links.csv", data_dir):
        facts.append(
            _fact(
                "RiskFactor",
                row["risk_factor"],
                "TRIGGERS_POLICY",
                "Policy",
                policy_names[row["policy_id"]],
                row["source_data"],
                row["evidence_text"],
            )
        )

    for row in _read_csv_rows("policy_intervention_links.csv", data_dir):
        facts.append(
            _fact(
                "Policy",
                policy_names[row["policy_id"]],
                "RECOMMENDS_INTERVENTION",
                "Intervention",
                intervention_names[row["intervention_id"]],
                row["source_data"],
                row["evidence_text"],
            )
        )

    for row in _read_csv_rows("student_risk_factors.csv", data_dir):
        student_name = student_names[row["student_id"]]
        facts.append(
            _fact(
                "Student",
                student_name,
                "HAS_RISK_FACTOR",
                "RiskFactor",
                row["risk_factor"],
                row["source_data"],
                row["evidence_text"],
            )
        )

    for row in _read_csv_rows("student_interventions.csv", data_dir):
        student_name = student_names[row["student_id"]]
        facts.append(
            _fact(
                "Student",
                student_name,
                "RECOMMENDS_INTERVENTION",
                "Intervention",
                intervention_names[row["intervention_id"]],
                row["source_data"],
                row["evidence_text"],
            )
        )

    for row in _read_csv_rows("student_course_context.csv", data_dir):
        student_name = student_names[row["student_id"]]
        facts.append(
            _fact(
                "Student",
                student_name,
                "ENROLLED_IN",
                "Course",
                row["course_id"],
                row["source_data"],
                row["evidence_text"],
            )
        )

    for row in _read_csv_rows("course_policy_links.csv", data_dir):
        facts.append(
            _fact(
                "Course",
                row["course_id"],
                "MENTIONED_IN",
                "Policy",
                policy_names[row["policy_id"]],
                row["source_data"],
                row["evidence_text"],
            )
        )

    for row in _read_csv_rows("students.csv", data_dir):
        student_name = f"{row['first_name']} {row['last_name']}"
        facts.append(
            _fact(
                "Student",
                student_name,
                "ADVISED_BY",
                "Advisor",
                row["advisor"],
                "students",
                f"{student_name} is advised by {row['advisor']}.",
            )
        )
        facts.append(
            _fact(
                "Student",
                student_name,
                "BELONGS_TO_PROGRAM",
                "Program",
                row["program"],
                "students",
                f"{student_name} is enrolled in {row['program']}.",
            )
        )

    return facts


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON array found in model response")
    payload = json.loads(match.group(0))
    if not isinstance(payload, list):
        raise ValueError("Expected a JSON array of graph facts")
    return payload


def _csv_documents_for_llm(data_dir: Path) -> list[tuple[str, str]]:
    documents: list[tuple[str, str]] = []
    for csv_name in (
        "policies.csv",
        "advising_notes.csv",
        "courses.csv",
        "risk_policy_links.csv",
        "policy_intervention_links.csv",
        "student_risk_factors.csv",
        "student_interventions.csv",
        "course_policy_links.csv",
    ):
        rows = _read_csv_rows(csv_name, data_dir)
        if not rows:
            continue
        documents.append((csv_name, json.dumps(rows, ensure_ascii=False, indent=2)))
    return documents


def extract_graph_facts_with_llm(data_dir: Path | None = None) -> list[GraphFact]:
    """Optional LLM extraction pass over policy and advising CSV content."""
    data_dir = data_dir or DATA_DIR
    facts: list[GraphFact] = []
    prompt_template = """
Extract knowledge-graph facts from the CSV-backed document below.

Return only a JSON array. Each item must use these keys:
- head_label: one of Student, Course, Policy, RiskFactor, Intervention, Advisor, Program
- head_name: string
- relation: one of ENROLLED_IN, HAS_RISK_FACTOR, TRIGGERS_POLICY, RECOMMENDS_INTERVENTION,
  ADVISED_BY, BELONGS_TO_PROGRAM, MENTIONED_IN
- tail_label: same label set as head_label
- tail_name: string
- evidence_text: short supporting quote from the document
- confidence: number between 0 and 1

Document: {source_doc}
Content:
{content}
"""
    for source_doc, content in _csv_documents_for_llm(data_dir):
        prompt = prompt_template.format(source_doc=source_doc, content=content)
        response = get_llm().invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        for item in _extract_json_array(text):
            facts.append(
                GraphFact(
                    head_label=str(item["head_label"]),
                    head_name=str(item["head_name"]),
                    relation=str(item["relation"]),
                    tail_label=str(item["tail_label"]),
                    tail_name=str(item["tail_name"]),
                    source_doc=source_doc,
                    evidence_text=str(item.get("evidence_text") or ""),
                    confidence=float(item.get("confidence") or 0.8),
                    term=DEFAULT_TERM,
                )
            )
    return facts


def extract_graph_facts(use_llm: bool = False, data_dir: Path | None = None) -> list[GraphFact]:
    """Return graph facts for Neo4j loading from CSV seed files."""
    data_dir = data_dir or DATA_DIR
    facts = build_graph_facts(data_dir=data_dir)
    if not use_llm:
        return facts

    try:
        llm_facts = extract_graph_facts_with_llm(data_dir=data_dir)
    except Exception:
        return facts

    seen = {(fact.head_name, fact.relation, fact.tail_name) for fact in facts}
    for fact in llm_facts:
        key = (fact.head_name, fact.relation, fact.tail_name)
        if key not in seen:
            facts.append(fact)
            seen.add(key)
    return facts
