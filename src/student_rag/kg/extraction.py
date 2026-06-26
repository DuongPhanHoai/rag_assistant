from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from student_rag.llm import get_llm
from student_rag.paths import DEFAULT_TERM, DOCS_DIR


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


def build_graph_facts() -> list[GraphFact]:
    """Build deterministic AutoSchemaKG-style facts from the sample markdown docs."""
    facts: list[GraphFact] = [
        _fact(
            "RiskFactor",
            "Irregular Attendance",
            "TRIGGERS_POLICY",
            "Policy",
            "Attendance Intervention Policy",
            "policies.md",
            "Attendance below 75 percent requires advisor follow-up.",
        ),
        _fact(
            "Policy",
            "Attendance Intervention Policy",
            "RECOMMENDS_INTERVENTION",
            "Intervention",
            "Weekly Lab Attendance",
            "policies.md",
            "Recommended interventions include weekly lab attendance.",
        ),
        _fact(
            "RiskFactor",
            "Balance Due Greater Than 500",
            "TRIGGERS_POLICY",
            "Policy",
            "Financial Hold Policy",
            "policies.md",
            "Students with overdue balances above 500 should meet financial aid before registration opens.",
        ),
        _fact(
            "Policy",
            "Financial Hold Policy",
            "RECOMMENDS_INTERVENTION",
            "Intervention",
            "Financial Aid Review",
            "policies.md",
            "Recommended interventions include financial aid review.",
        ),
        _fact(
            "Policy",
            "Academic Risk Policy",
            "RECOMMENDS_INTERVENTION",
            "Intervention",
            "Advisor Meeting",
            "policies.md",
            "High-risk students should receive a coordinated plan.",
        ),
        _fact(
            "Policy",
            "Scholarship Support Policy",
            "RECOMMENDS_INTERVENTION",
            "Intervention",
            "Peer Tutoring",
            "policies.md",
            "Scholarship support is prioritized for students with strong academic standing.",
        ),
        _fact(
            "Student",
            "Carlos Reyes",
            "HAS_RISK_FACTOR",
            "RiskFactor",
            "Irregular Attendance",
            "advising_notes.md",
            "Notes mention irregular attendance and difficulty completing programming labs.",
        ),
        _fact(
            "Student",
            "Carlos Reyes",
            "HAS_RISK_FACTOR",
            "RiskFactor",
            "Balance Due Greater Than 500",
            "advising_notes.md",
            "Notes mention overdue fees.",
        ),
        _fact(
            "Student",
            "Owen Smith",
            "HAS_RISK_FACTOR",
            "RiskFactor",
            "Irregular Attendance",
            "advising_notes.md",
            "Advising notes mention missed labs and late project work.",
        ),
        _fact(
            "Student",
            "Owen Smith",
            "HAS_RISK_FACTOR",
            "RiskFactor",
            "Balance Due Greater Than 500",
            "advising_notes.md",
            "Advising notes mention a large unpaid fee balance.",
        ),
        _fact(
            "Student",
            "Noah Patel",
            "HAS_RISK_FACTOR",
            "RiskFactor",
            "Irregular Attendance",
            "advising_notes.md",
            "Commute issues affected March attendance.",
        ),
        _fact(
            "Student",
            "Noah Patel",
            "RECOMMENDS_INTERVENTION",
            "Intervention",
            "Weekly Lab Attendance",
            "advising_notes.md",
            "Advisor recommended a catch-up plan with weekly lab attendance.",
        ),
        _fact(
            "Student",
            "Maya Tran",
            "RECOMMENDS_INTERVENTION",
            "Intervention",
            "Peer Tutoring",
            "advising_notes.md",
            "She is a good candidate for peer tutoring.",
        ),
        _fact(
            "Student",
            "Minh Nguyen",
            "RECOMMENDS_INTERVENTION",
            "Intervention",
            "Study-Group Placement",
            "advising_notes.md",
            "Advisor suggested study-group participation before the next assessment.",
        ),
        _fact(
            "Student",
            "Owen Smith",
            "RECOMMENDS_INTERVENTION",
            "Intervention",
            "Advisor Meeting",
            "advising_notes.md",
            "Intervention team recommended a meeting with the advisor and financial aid.",
        ),
        _fact(
            "Student",
            "Carlos Reyes",
            "ENROLLED_IN",
            "Course",
            "C102",
            "course_descriptions.md",
            "Carlos is at high risk in Database Fundamentals.",
        ),
        _fact(
            "Student",
            "Carlos Reyes",
            "ENROLLED_IN",
            "Course",
            "C101",
            "course_descriptions.md",
            "Carlos is at high risk in Python for Analytics.",
        ),
        _fact(
            "Course",
            "C101",
            "MENTIONED_IN",
            "Policy",
            "Academic Risk Policy",
            "course_descriptions.md",
            "Python for Analytics is a core analytics course.",
        ),
    ]

    advisor_map = {
        "Maya Tran": "Dr. Rivera",
        "Noah Patel": "Prof. Chen",
        "Lina Garcia": "Dr. Rivera",
        "Owen Smith": "Prof. Malik",
        "Aisha Khan": "Prof. Chen",
        "Minh Nguyen": "Dr. Santos",
        "Emma Brown": "Dr. Santos",
        "Carlos Reyes": "Prof. Malik",
    }
    program_map = {
        "Maya Tran": "Data Analytics",
        "Noah Patel": "Software Engineering",
        "Lina Garcia": "Business Analytics",
        "Owen Smith": "Software Engineering",
        "Aisha Khan": "Information Systems",
        "Minh Nguyen": "Data Analytics",
        "Emma Brown": "Business Analytics",
        "Carlos Reyes": "Information Systems",
    }

    for student_name, advisor in advisor_map.items():
        facts.append(
            _fact(
                "Student",
                student_name,
                "ADVISED_BY",
                "Advisor",
                advisor,
                "students.csv",
                f"{student_name} is advised by {advisor}.",
            )
        )
        facts.append(
            _fact(
                "Student",
                student_name,
                "BELONGS_TO_PROGRAM",
                "Program",
                program_map[student_name],
                "students.csv",
                f"{student_name} is enrolled in {program_map[student_name]}.",
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


def extract_graph_facts_with_llm(docs_dir: Path | None = None) -> list[GraphFact]:
    """Optional LLM extraction pass in AutoSchemaKG style over markdown docs."""
    docs_dir = docs_dir or DOCS_DIR
    facts: list[GraphFact] = []
    prompt_template = """
Extract knowledge-graph facts from the markdown document below.

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
    for path in sorted(docs_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        prompt = prompt_template.format(source_doc=path.name, content=content)
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
                    source_doc=path.name,
                    evidence_text=str(item.get("evidence_text") or ""),
                    confidence=float(item.get("confidence") or 0.8),
                    term=DEFAULT_TERM,
                )
            )
    return facts


def extract_graph_facts(use_llm: bool = False, docs_dir: Path | None = None) -> list[GraphFact]:
    """Return graph facts for Neo4j loading.

    The default path uses deterministic extraction from the sample docs so the showcase
    works without an LLM. Pass use_llm=True for an additional AutoSchemaKG-style pass.
    """
    facts = build_graph_facts()
    if not use_llm:
        return facts

    try:
        llm_facts = extract_graph_facts_with_llm(docs_dir=docs_dir)
    except Exception:
        return facts

    seen = {(fact.head_name, fact.relation, fact.tail_name) for fact in facts}
    for fact in llm_facts:
        key = (fact.head_name, fact.relation, fact.tail_name)
        if key not in seen:
            facts.append(fact)
            seen.add(key)
    return facts
