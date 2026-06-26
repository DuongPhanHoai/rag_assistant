from __future__ import annotations

import re
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from student_rag.kg.extraction import GraphFact
from student_rag.paths import NEO4J_DATABASE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER


MAX_CYPHER_ROWS = 50
BLOCKED_CYPHER_PATTERN = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV|CALL\s*\{)\b",
    re.IGNORECASE,
)
ALLOWED_CYPHER_START = re.compile(
    r"^\s*(MATCH|OPTIONAL\s+MATCH|WITH|UNWIND|RETURN)\b",
    re.IGNORECASE,
)


class Neo4jUnavailableError(RuntimeError):
    pass


def is_neo4j_configured() -> bool:
    return bool(NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD)


def _get_driver():
    if not is_neo4j_configured():
        raise Neo4jUnavailableError(
            "Neo4j is not configured. Set NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD."
        )
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
        connection_timeout=5.0,
    )


def _rows_to_dicts(records: list[Any]) -> list[dict[str, Any]]:
    return [dict(record) for record in records]


def validate_read_only_cypher(cypher: str) -> str:
    query = cypher.strip().rstrip(";")
    if not query:
        raise ValueError("Cypher query cannot be empty.")
    if BLOCKED_CYPHER_PATTERN.search(query):
        raise ValueError("Only read-only Cypher is allowed.")
    if not ALLOWED_CYPHER_START.match(query):
        raise ValueError("Cypher must start with MATCH, OPTIONAL MATCH, WITH, UNWIND, or RETURN.")
    if " LIMIT " not in query.upper():
        query = f"{query}\nLIMIT {MAX_CYPHER_ROWS}"
    return query


def run_read_only_cypher(cypher: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = validate_read_only_cypher(cypher)
    params = params or {}
    try:
        with _get_driver() as driver:
            with driver.session(database=NEO4J_DATABASE) as session:
                result = session.run(query, params)
                rows = _rows_to_dicts(result.data())
    except ServiceUnavailable as exc:
        raise Neo4jUnavailableError(
            "Neo4j is unavailable. Start Neo4j and run scripts/build_student_kg.py."
        ) from exc
    except Neo4jError as exc:
        raise ValueError(f"Neo4j query failed: {exc}") from exc

    return {
        "cypher": query,
        "params": params,
        "row_count": len(rows),
        "rows": rows,
    }


def ensure_constraints() -> None:
    statements = [
        "CREATE CONSTRAINT student_name IF NOT EXISTS FOR (s:Student) REQUIRE s.name IS UNIQUE",
        "CREATE CONSTRAINT policy_name IF NOT EXISTS FOR (p:Policy) REQUIRE p.name IS UNIQUE",
        "CREATE CONSTRAINT course_id IF NOT EXISTS FOR (c:Course) REQUIRE c.course_id IS UNIQUE",
        "CREATE CONSTRAINT risk_factor_name IF NOT EXISTS FOR (r:RiskFactor) REQUIRE r.name IS UNIQUE",
        "CREATE CONSTRAINT intervention_name IF NOT EXISTS FOR (i:Intervention) REQUIRE i.name IS UNIQUE",
        "CREATE CONSTRAINT advisor_name IF NOT EXISTS FOR (a:Advisor) REQUIRE a.name IS UNIQUE",
        "CREATE CONSTRAINT program_name IF NOT EXISTS FOR (p:Program) REQUIRE p.name IS UNIQUE",
    ]
    with _get_driver() as driver:
        with driver.session(database=NEO4J_DATABASE) as session:
            for statement in statements:
                session.run(statement)


def clear_graph() -> None:
    with _get_driver() as driver:
        with driver.session(database=NEO4J_DATABASE) as session:
            session.run("MATCH (n) DETACH DELETE n")


def _merge_node(tx: Any, label: str, name: str, props: dict[str, Any]) -> None:
    key = "course_id" if label == "Course" else "name"
    tx.run(
        f"""
        MERGE (n:{label} {{{key}: $name}})
        SET n += $props
        """,
        name=name,
        props=props,
    )


def _merge_relationship(
    tx: Any,
    head_label: str,
    head_name: str,
    relation: str,
    tail_label: str,
    tail_name: str,
    props: dict[str, Any],
) -> None:
    head_key = "course_id" if head_label == "Course" else "name"
    tail_key = "course_id" if tail_label == "Course" else "name"
    tx.run(
        f"""
        MATCH (h:{head_label} {{{head_key}: $head_name}})
        MATCH (t:{tail_label} {{{tail_key}: $tail_name}})
        MERGE (h)-[r:{relation}]->(t)
        SET r += $props
        """,
        head_name=head_name,
        tail_name=tail_name,
        props=props,
    )


def load_graph_facts(facts: list[GraphFact], reset: bool = True) -> dict[str, Any]:
    ensure_constraints()
    if reset:
        clear_graph()

    with _get_driver() as driver:
        with driver.session(database=NEO4J_DATABASE) as session:
            for fact in facts:
                head_props = {"name": fact.head_name}
                tail_props = {"name": fact.tail_name}
                if fact.head_label == "Course":
                    head_props = {"course_id": fact.head_name, "name": fact.head_name}
                if fact.tail_label == "Course":
                    tail_props = {"course_id": fact.tail_name, "name": fact.tail_name}

                session.execute_write(_merge_node, fact.head_label, fact.head_name, head_props)
                session.execute_write(_merge_node, fact.tail_label, fact.tail_name, tail_props)
                session.execute_write(
                    _merge_relationship,
                    fact.head_label,
                    fact.head_name,
                    fact.relation,
                    fact.tail_label,
                    fact.tail_name,
                    {
                        "source_doc": fact.source_doc,
                        "evidence_text": fact.evidence_text,
                        "confidence": fact.confidence,
                        "term": fact.term,
                    },
                )

    return {"loaded_facts": len(facts), "reset": reset}


def get_student_graph_context(student_name: str) -> dict[str, Any]:
    cypher = """
    MATCH (s:Student {name: $student_name})
    OPTIONAL MATCH (s)-[r]->(n)
    RETURN s.name AS student_name, type(r) AS relation, labels(n) AS target_labels,
           coalesce(n.name, n.course_id) AS target_name, r.source_doc AS source_doc,
           r.evidence_text AS evidence_text
    ORDER BY relation, target_name
    """
    result = run_read_only_cypher(cypher, {"student_name": student_name})
    return {
        "student_name": student_name,
        "context": result["rows"],
        "row_count": result["row_count"],
    }


def get_policy_intervention_path(student_name: str) -> dict[str, Any]:
    cypher = """
    MATCH (s:Student {name: $student_name})-[r1:HAS_RISK_FACTOR]->(rf:RiskFactor)
    OPTIONAL MATCH (rf)-[r2:TRIGGERS_POLICY]->(p:Policy)
    OPTIONAL MATCH (p)-[r3:RECOMMENDS_INTERVENTION]->(i:Intervention)
    RETURN s.name AS student_name, rf.name AS risk_factor, p.name AS policy,
           i.name AS intervention,
           coalesce(r3.source_doc, r2.source_doc, r1.source_doc) AS source_doc
    ORDER BY risk_factor, policy, intervention
    """
    result = run_read_only_cypher(cypher, {"student_name": student_name})
    return {
        "student_name": student_name,
        "paths": result["rows"],
        "row_count": result["row_count"],
    }


def get_related_risk_factors(student_name: str) -> dict[str, Any]:
    cypher = """
    MATCH (s:Student {name: $student_name})-[r:HAS_RISK_FACTOR]->(rf:RiskFactor)
    RETURN s.name AS student_name, rf.name AS risk_factor, r.source_doc AS source_doc,
           r.evidence_text AS evidence_text
    ORDER BY risk_factor
    """
    result = run_read_only_cypher(cypher, {"student_name": student_name})
    return {
        "student_name": student_name,
        "risk_factors": result["rows"],
        "row_count": result["row_count"],
    }


def query_knowledge_graph(cypher: str) -> dict[str, Any]:
    return run_read_only_cypher(cypher)


def search_graph_context(query: str, limit: int = 8) -> dict[str, Any]:
    """Search graph nodes and evidence text for policy or intervention context."""
    cypher = """
    MATCH (n)-[r]->(m)
    WHERE toLower(coalesce(n.name, n.course_id, '')) CONTAINS toLower($query)
       OR toLower(coalesce(m.name, m.course_id, '')) CONTAINS toLower($query)
       OR toLower(coalesce(r.evidence_text, '')) CONTAINS toLower($query)
    RETURN labels(n) AS labels, coalesce(n.name, n.course_id) AS name,
           type(r) AS relation, coalesce(m.name, m.course_id) AS related_name,
           r.source_doc AS source_doc, r.evidence_text AS evidence_text
    LIMIT $limit
    """
    result = run_read_only_cypher(cypher, {"query": query, "limit": limit})
    return {
        "query": query,
        "matches": result["rows"],
        "row_count": result["row_count"],
    }
