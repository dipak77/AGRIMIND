"""Neo4j knowledge graph store + multi-hop path retrieval."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from memory.graph.seed_graph import default_graph_edges, default_graph_nodes

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w\u0900-\u097F]+", re.UNICODE)


@dataclass
class GraphPathHit:
    path_id: str
    nodes: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    confidence: float
    is_approved: bool
    citations: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""


class GraphStore(Protocol):
    def ping(self) -> bool: ...
    def seed_default(self) -> dict[str, Any]: ...
    def upsert_nodes(self, nodes: list[dict[str, Any]]) -> int: ...
    def upsert_edges(self, edges: list[dict[str, Any]]) -> int: ...
    def multi_hop_paths(self, query: str, top_k: int = 5) -> list[GraphPathHit]: ...
    def count_nodes(self) -> int: ...
    def close(self) -> None: ...


def _keywords(query: str) -> list[str]:
    toks = [t.lower() for t in _TOKEN_RE.findall(query or "") if len(t) >= 2]
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:12]


def _path_summary(nodes: list[dict[str, Any]], rels: list[dict[str, Any]]) -> str:
    names = [str(n.get("name") or n.get("id")) for n in nodes]
    rel_types = [str(r.get("relation") or r.get("type") or "") for r in rels]
    if len(names) >= 2 and rel_types:
        parts = [names[0]]
        for i, r in enumerate(rel_types):
            parts.append(f"-[{r}]->")
            if i + 1 < len(names):
                parts.append(names[i + 1])
        return " ".join(parts)
    return " → ".join(names)


class InMemoryGraphStore:
    """Unit-test / offline graph store with the same API as Neo4jGraphStore."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        return None

    def count_nodes(self) -> int:
        return len(self.nodes)

    def upsert_nodes(self, nodes: list[dict[str, Any]]) -> int:
        for n in nodes:
            nid = str(n["id"])
            self.nodes[nid] = {**n, "id": nid}
        return len(nodes)

    def upsert_edges(self, edges: list[dict[str, Any]]) -> int:
        for e in edges:
            self.edges.append(dict(e))
        return len(edges)

    def seed_default(self) -> dict[str, Any]:
        nn = self.upsert_nodes(default_graph_nodes())
        ne = self.upsert_edges(default_graph_edges())
        return {"nodes": nn, "edges": ne, "backend": "in_memory"}

    def multi_hop_paths(self, query: str, top_k: int = 5) -> list[GraphPathHit]:
        kws = _keywords(query)
        if not kws:
            return []

        def matches(node: dict[str, Any]) -> bool:
            blob = " ".join(
                [
                    str(node.get("name") or ""),
                    str(node.get("id") or ""),
                    " ".join(node.get("aliases") or []),
                ]
            ).lower()
            return any(k in blob for k in kws)

        # Index edges by source
        out_edges: dict[str, list[dict[str, Any]]] = {}
        for e in self.edges:
            out_edges.setdefault(str(e["source"]), []).append(e)

        hits: list[GraphPathHit] = []
        for nid, node in self.nodes.items():
            if not matches(node):
                continue
            # 1-hop and 2-hop DFS
            for e1 in out_edges.get(nid, []):
                if not e1.get("is_approved", True) or e1.get("banned"):
                    continue
                n2 = self.nodes.get(str(e1["target"]))
                if not n2 or n2.get("banned") or not n2.get("is_approved", True):
                    continue
                path_nodes = [node, n2]
                path_rels = [e1]
                conf = float(e1.get("confidence") or 0.7)
                # extend 2nd hop
                for e2 in out_edges.get(str(n2["id"]), []):
                    if not e2.get("is_approved", True) or e2.get("banned"):
                        continue
                    n3 = self.nodes.get(str(e2["target"]))
                    if not n3 or n3.get("banned") or not n3.get("is_approved", True):
                        continue
                    # skip recommending banned chemicals even if edge slipped
                    if n3.get("type") == "Chemical" and n3.get("banned"):
                        continue
                    nodes3 = [node, n2, n3]
                    rels3 = [e1, e2]
                    conf3 = min(float(e1.get("confidence") or 0.7), float(e2.get("confidence") or 0.7))
                    hits.append(self._hit(nodes3, rels3, conf3))
                hits.append(self._hit(path_nodes, path_rels, conf))

        # Also match middle/end nodes (e.g. query "bollworm")
        for e in self.edges:
            if not e.get("is_approved", True) or e.get("banned"):
                continue
            src = self.nodes.get(str(e["source"]))
            tgt = self.nodes.get(str(e["target"]))
            if not src or not tgt:
                continue
            if tgt.get("banned") or not tgt.get("is_approved", True):
                continue
            if matches(src) or matches(tgt):
                hits.append(self._hit([src, tgt], [e], float(e.get("confidence") or 0.7)))

        # de-dupe by summary
        uniq: dict[str, GraphPathHit] = {}
        for h in hits:
            key = h.summary
            if key not in uniq or h.confidence > uniq[key].confidence:
                uniq[key] = h
        ranked = sorted(uniq.values(), key=lambda x: x.confidence, reverse=True)
        return ranked[:top_k]

    def _hit(
        self,
        nodes: list[dict[str, Any]],
        rels: list[dict[str, Any]],
        confidence: float,
    ) -> GraphPathHit:
        citations = []
        for r in rels:
            citations.append(
                {
                    "source_id": r.get("source_id") or "unknown",
                    "source_type": "knowledge_graph",
                    "url_or_path": r.get("url_or_path") or "",
                    "checksum": r.get("checksum") or "",
                    "span": r.get("span") or r.get("relation"),
                    "title": f"KG:{r.get('relation')}",
                    "excerpt": _path_summary(nodes, rels),
                    "confidence": float(r.get("confidence") or confidence),
                }
            )
        approved = all(r.get("is_approved", True) for r in rels) and all(
            n.get("is_approved", True) for n in nodes
        )
        return GraphPathHit(
            path_id=str(uuid.uuid4()),
            nodes=[{"id": n.get("id"), "type": n.get("type"), "name": n.get("name")} for n in nodes],
            relationships=[
                {
                    "relation": r.get("relation"),
                    "source": r.get("source"),
                    "target": r.get("target"),
                    "source_id": r.get("source_id"),
                    "is_approved": r.get("is_approved", True),
                }
                for r in rels
            ],
            confidence=confidence,
            is_approved=approved,
            citations=citations,
            summary=_path_summary(nodes, rels),
        )


class Neo4jGraphStore:
    """Live Neo4j graph store."""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "agrimind123",
    ) -> None:
        self.uri = uri
        self.user = user
        self.password = password
        self._driver = None

    def _driver_get(self):
        if self._driver is not None:
            return self._driver
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("neo4j driver not installed") from exc
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        return self._driver

    def ping(self) -> bool:
        try:
            driver = self._driver_get()
            with driver.session() as session:
                session.run("RETURN 1 AS ok").single()
            return True
        except Exception as exc:
            logger.warning("neo4j_ping_failed: %s", exc)
            return False

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def count_nodes(self) -> int:
        driver = self._driver_get()
        with driver.session() as session:
            rec = session.run("MATCH (n) RETURN count(n) AS c").single()
            return int(rec["c"]) if rec else 0

    def ensure_constraints(self) -> None:
        driver = self._driver_get()
        stmts = [
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE",
        ]
        with driver.session() as session:
            for s in stmts:
                try:
                    session.run(s)
                except Exception:
                    # older neo4j syntax fallback
                    try:
                        session.run(
                            "CREATE CONSTRAINT ON (n:Entity) ASSERT n.id IS UNIQUE"
                        )
                    except Exception:
                        pass

    def upsert_nodes(self, nodes: list[dict[str, Any]]) -> int:
        self.ensure_constraints()
        driver = self._driver_get()
        # Without APOC, set dynamic label via separate MERGE patterns for known types
        simple = """
        MERGE (n:Entity {id: $id})
        SET n.name = $name,
            n.type = $type,
            n.aliases = $aliases,
            n.source_id = $source_id,
            n.is_approved = $is_approved,
            n.banned = $banned,
            n.safety_critical = $safety_critical,
            n.description = $description
        RETURN n
        """
        with driver.session() as session:
            for n in nodes:
                session.run(
                    simple,
                    id=str(n["id"]),
                    name=n.get("name") or "",
                    type=n.get("type") or "Entity",
                    aliases=list(n.get("aliases") or []),
                    source_id=n.get("source_id") or "",
                    is_approved=bool(n.get("is_approved", True)),
                    banned=bool(n.get("banned", False)),
                    safety_critical=bool(n.get("safety_critical", False)),
                    description=n.get("description") or "",
                )
                # add type label if possible (Neo4j 5+)
                t = re.sub(r"[^A-Za-z]", "", str(n.get("type") or "Entity"))
                if t:
                    try:
                        session.run(f"MATCH (n:Entity {{id: $id}}) SET n:{t}", id=str(n["id"]))
                    except Exception:
                        pass
        return len(nodes)

    def upsert_edges(self, edges: list[dict[str, Any]]) -> int:
        driver = self._driver_get()
        # Use generic RELATED for storage + relation property (avoids dynamic rel type issues)
        cypher = """
        MATCH (a:Entity {id: $source})
        MATCH (b:Entity {id: $target})
        MERGE (a)-[r:KG_REL {relation: $relation, source_id: $source_id}]->(b)
        SET r.confidence = $confidence,
            r.is_approved = $is_approved,
            r.banned = $banned,
            r.url_or_path = $url_or_path,
            r.checksum = $checksum,
            r.span = $span,
            r.safety_critical = $safety_critical
        RETURN r
        """
        with driver.session() as session:
            for e in edges:
                session.run(
                    cypher,
                    source=str(e["source"]),
                    target=str(e["target"]),
                    relation=str(e.get("relation") or "RELATED_TO"),
                    source_id=str(e.get("source_id") or ""),
                    confidence=float(e.get("confidence") or 0.7),
                    is_approved=bool(e.get("is_approved", True)),
                    banned=bool(e.get("banned", False)),
                    url_or_path=str(e.get("url_or_path") or ""),
                    checksum=str(e.get("checksum") or ""),
                    span=str(e.get("span") or ""),
                    safety_critical=bool(e.get("safety_critical", False)),
                )
        return len(edges)

    def seed_default(self) -> dict[str, Any]:
        nn = self.upsert_nodes(default_graph_nodes())
        ne = self.upsert_edges(default_graph_edges())
        return {"nodes": nn, "edges": ne, "backend": "neo4j", "uri": self.uri}

    def multi_hop_paths(self, query: str, top_k: int = 5) -> list[GraphPathHit]:
        kws = _keywords(query)
        if not kws:
            return []
        driver = self._driver_get()
        # Multi-hop: (start)-[r1]->(mid)-[r2]->(end) with approved filters
        cypher = """
        MATCH (a:Entity)-[r1:KG_REL]->(b:Entity)
        WHERE a.is_approved = true AND b.is_approved = true
          AND coalesce(r1.is_approved, true) = true
          AND coalesce(r1.banned, false) = false
          AND coalesce(b.banned, false) = false
          AND (
            any(k IN $kws WHERE toLower(a.name) CONTAINS k
                OR any(al IN coalesce(a.aliases, []) WHERE toLower(al) CONTAINS k)
                OR toLower(a.id) CONTAINS k)
            OR any(k IN $kws WHERE toLower(b.name) CONTAINS k
                OR any(al IN coalesce(b.aliases, []) WHERE toLower(al) CONTAINS k)
                OR toLower(b.id) CONTAINS k)
          )
        OPTIONAL MATCH (b)-[r2:KG_REL]->(c:Entity)
        WHERE c IS NULL OR (
            c.is_approved = true
            AND coalesce(c.banned, false) = false
            AND coalesce(r2.is_approved, true) = true
            AND coalesce(r2.banned, false) = false
          )
        RETURN a, r1, b, r2, c
        LIMIT $limit
        """
        hits: list[GraphPathHit] = []
        with driver.session() as session:
            records = session.run(cypher, kws=kws, limit=top_k * 4)
            for rec in records:
                a = dict(rec["a"])
                b = dict(rec["b"])
                r1 = dict(rec["r1"])
                nodes = [
                    {"id": a.get("id"), "type": a.get("type"), "name": a.get("name")},
                    {"id": b.get("id"), "type": b.get("type"), "name": b.get("name")},
                ]
                rels = [
                    {
                        "relation": r1.get("relation"),
                        "source": a.get("id"),
                        "target": b.get("id"),
                        "source_id": r1.get("source_id"),
                        "is_approved": r1.get("is_approved", True),
                        "confidence": r1.get("confidence", 0.7),
                        "url_or_path": r1.get("url_or_path"),
                        "checksum": r1.get("checksum"),
                        "span": r1.get("span"),
                    }
                ]
                conf = float(r1.get("confidence") or 0.7)
                c = rec.get("c")
                r2 = rec.get("r2")
                if c is not None and r2 is not None:
                    c = dict(c)
                    r2 = dict(r2)
                    if c.get("type") == "Chemical" and c.get("banned"):
                        pass  # skip banned extension
                    else:
                        nodes.append(
                            {"id": c.get("id"), "type": c.get("type"), "name": c.get("name")}
                        )
                        rels.append(
                            {
                                "relation": r2.get("relation"),
                                "source": b.get("id"),
                                "target": c.get("id"),
                                "source_id": r2.get("source_id"),
                                "is_approved": r2.get("is_approved", True),
                                "confidence": r2.get("confidence", 0.7),
                                "url_or_path": r2.get("url_or_path"),
                                "checksum": r2.get("checksum"),
                                "span": r2.get("span"),
                            }
                        )
                        conf = min(conf, float(r2.get("confidence") or 0.7))
                citations = []
                for r in rels:
                    citations.append(
                        {
                            "source_id": r.get("source_id") or "unknown",
                            "source_type": "knowledge_graph",
                            "url_or_path": r.get("url_or_path") or "",
                            "checksum": r.get("checksum") or "",
                            "span": r.get("span") or r.get("relation"),
                            "title": f"KG:{r.get('relation')}",
                            "excerpt": _path_summary(nodes, rels),
                            "confidence": float(r.get("confidence") or conf),
                        }
                    )
                hits.append(
                    GraphPathHit(
                        path_id=str(uuid.uuid4()),
                        nodes=nodes,
                        relationships=rels,
                        confidence=conf,
                        is_approved=True,
                        citations=citations,
                        summary=_path_summary(nodes, rels),
                    )
                )
        uniq: dict[str, GraphPathHit] = {}
        for h in hits:
            if h.summary not in uniq or h.confidence > uniq[h.summary].confidence:
                uniq[h.summary] = h
        return sorted(uniq.values(), key=lambda x: x.confidence, reverse=True)[:top_k]
