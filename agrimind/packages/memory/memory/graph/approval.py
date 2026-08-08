"""Expert approval gate for chemical/dosage knowledge-graph writes (E2)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


HIGH_RISK_NODE_TYPES = frozenset({"Chemical", "Dosage", "Treatment"})
HIGH_RISK_RELATIONS = frozenset({"TREATED_BY", "HAS_DOSAGE", "CONTRAINDICATED_WITH"})


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class GraphWriteProposal:
    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: str = "node"  # node | edge
    payload: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "high"  # high | low
    status: str = ProposalStatus.PENDING.value
    reason: str = ""
    submitted_by: str = "system"
    reviewed_by: str | None = None
    review_notes: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    decided_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphWriteProposal":
        fields = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in fields})


def is_high_risk_node(node: dict[str, Any]) -> bool:
    t = str(node.get("type") or "")
    if t in HIGH_RISK_NODE_TYPES:
        return True
    if node.get("safety_critical") or node.get("banned"):
        return True
    return False


def is_high_risk_edge(edge: dict[str, Any]) -> bool:
    rel = str(edge.get("relation") or "")
    if rel in HIGH_RISK_RELATIONS:
        return True
    return bool(edge.get("safety_critical"))


class GraphApprovalQueue:
    """Staging queue: high-risk KG writes need expert approval before apply."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._items: dict[str, GraphWriteProposal] = {}
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._load()

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                p = GraphWriteProposal.from_dict(json.loads(line))
                self._items[p.proposal_id] = p

    def _persist(self, proposal: GraphWriteProposal) -> None:
        if not self.path:
            return
        # rewrite file for simplicity (small queues)
        with self.path.open("w", encoding="utf-8") as f:
            for p in self._items.values():
                f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")

    def submit(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        submitted_by: str = "system",
        reason: str = "",
    ) -> GraphWriteProposal:
        risk = "low"
        if kind == "node" and is_high_risk_node(payload):
            risk = "high"
        if kind == "edge" and is_high_risk_edge(payload):
            risk = "high"
        # low-risk can be auto-approved
        status = (
            ProposalStatus.PENDING.value
            if risk == "high"
            else ProposalStatus.APPROVED.value
        )
        prop = GraphWriteProposal(
            kind=kind,
            payload=payload,
            risk_level=risk,
            status=status,
            submitted_by=submitted_by,
            reason=reason or ("high_risk_requires_expert" if risk == "high" else "auto"),
            decided_at=datetime.now(timezone.utc).isoformat()
            if status == ProposalStatus.APPROVED.value
            else None,
            reviewed_by="auto" if status == ProposalStatus.APPROVED.value else None,
        )
        self._items[prop.proposal_id] = prop
        self._persist(prop)
        return prop

    def list(self, status: str | None = "pending") -> list[GraphWriteProposal]:
        items = list(self._items.values())
        if status:
            items = [p for p in items if p.status == status]
        return sorted(items, key=lambda p: p.created_at, reverse=True)

    def decide(
        self,
        proposal_id: str,
        decision: str,
        *,
        reviewed_by: str = "expert",
        notes: str = "",
    ) -> GraphWriteProposal:
        if proposal_id not in self._items:
            raise KeyError(f"proposal not found: {proposal_id}")
        if decision not in (
            ProposalStatus.APPROVED.value,
            ProposalStatus.REJECTED.value,
        ):
            raise ValueError("decision must be approved|rejected")
        p = self._items[proposal_id]
        p.status = decision
        p.reviewed_by = reviewed_by
        p.review_notes = notes
        p.decided_at = datetime.now(timezone.utc).isoformat()
        self._items[proposal_id] = p
        self._persist(p)
        return p

    def apply_approved(
        self,
        graph_store: Any,
        proposal_id: str,
    ) -> dict[str, Any]:
        """Apply an approved proposal to the graph store (upsert)."""
        p = self._items.get(proposal_id)
        if not p:
            raise KeyError(f"proposal not found: {proposal_id}")
        if p.status != ProposalStatus.APPROVED.value:
            raise PermissionError(
                f"proposal {proposal_id} is {p.status}; only approved writes apply"
            )
        if p.kind == "node":
            n = graph_store.upsert_nodes([p.payload])
            return {"applied": "node", "count": n, "proposal_id": proposal_id}
        if p.kind == "edge":
            n = graph_store.upsert_edges([p.payload])
            return {"applied": "edge", "count": n, "proposal_id": proposal_id}
        raise ValueError(f"unknown kind: {p.kind}")


class GatedGraphWriter:
    """
    Write path for KG mutations.
    High-risk chemical/dosage nodes/edges go to approval queue instead of direct write.
    """

    def __init__(self, graph_store: Any, queue: GraphApprovalQueue) -> None:
        self.graph = graph_store
        self.queue = queue

    def write_node(
        self,
        node: dict[str, Any],
        *,
        submitted_by: str = "system",
        force_direct: bool = False,
    ) -> dict[str, Any]:
        if force_direct or not is_high_risk_node(node):
            if is_high_risk_node(node) and not node.get("is_approved", False):
                # still gate unapproved high-risk
                prop = self.queue.submit(
                    "node", node, submitted_by=submitted_by, reason="high_risk_unapproved"
                )
                return {"status": prop.status, "proposal": prop.to_dict(), "written": False}
            n = self.graph.upsert_nodes([node])
            return {"status": "written", "count": n, "written": True}

        prop = self.queue.submit(
            "node", node, submitted_by=submitted_by, reason="high_risk_requires_expert"
        )
        return {
            "status": prop.status,
            "proposal": prop.to_dict(),
            "written": prop.status == ProposalStatus.APPROVED.value,
        }

    def write_edge(
        self,
        edge: dict[str, Any],
        *,
        submitted_by: str = "system",
        force_direct: bool = False,
    ) -> dict[str, Any]:
        if force_direct or not is_high_risk_edge(edge):
            if is_high_risk_edge(edge) and not edge.get("is_approved", False):
                prop = self.queue.submit(
                    "edge", edge, submitted_by=submitted_by, reason="high_risk_unapproved"
                )
                return {"status": prop.status, "proposal": prop.to_dict(), "written": False}
            n = self.graph.upsert_edges([edge])
            return {"status": "written", "count": n, "written": True}

        prop = self.queue.submit(
            "edge", edge, submitted_by=submitted_by, reason="high_risk_requires_expert"
        )
        return {
            "status": prop.status,
            "proposal": prop.to_dict(),
            "written": prop.status == ProposalStatus.APPROVED.value,
        }
