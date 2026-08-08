"""Expert console — reviews, graph approvals (E2), feedback visibility (E1)."""

from __future__ import annotations

import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agrimind_kernel.feedback.events import (
    FeedbackEvent,
    FeedbackType,
    build_feedback_store,
)

logger = structlog.get_logger()

# Ensure memory package import for graph approval
_MEM = Path(__file__).resolve().parents[2] / "packages" / "memory"
if _MEM.exists() and str(_MEM) not in sys.path:
    sys.path.insert(0, str(_MEM))


class ReviewItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query_text: str
    draft_answer: str
    reason: str
    status: Literal["pending", "approved", "rejected"] = "pending"
    query_id: str | None = None
    confidence: float | None = None


class Decision(BaseModel):
    item_id: str
    decision: Literal["approved", "rejected"]
    notes: str = ""
    reviewed_by: str = "expert"


class GraphNodeProposal(BaseModel):
    id: str
    type: str
    name: str
    aliases: list[str] = []
    source_id: str = "expert"
    is_approved: bool = False
    safety_critical: bool = False
    banned: bool = False
    description: str = ""
    submitted_by: str = "system"


class GraphEdgeProposal(BaseModel):
    source: str
    target: str
    relation: str
    source_id: str = "expert"
    confidence: float = 0.8
    is_approved: bool = False
    safety_critical: bool = False
    banned: bool = False
    submitted_by: str = "system"


class GraphDecision(BaseModel):
    proposal_id: str
    decision: Literal["approved", "rejected"]
    reviewed_by: str = "agronomist"
    notes: str = ""
    apply: bool = True  # apply to graph store if approved


class ExpertCorrection(BaseModel):
    query_id: str | None = None
    query_text: str
    original_answer: str = ""
    corrected_answer: str
    expert_id: str = "expert"
    reason: str = ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    from memory.graph.approval import GraphApprovalQueue, GatedGraphWriter
    from memory.graph.neo4j_store import InMemoryGraphStore

    logger.info("expert-console-api starting")
    app.state.review_queue: list[dict] = []
    # FEEDBACK_STORE=auto|postgres|jsonl|memory — auto tries POSTGRES_DSN then JSONL
    from agrimind_kernel.config.settings import get_settings

    _settings = get_settings()
    app.state.feedback = build_feedback_store(
        backend=os.getenv("FEEDBACK_STORE", _settings.feedback_store),
        path=os.getenv("FEEDBACK_PATH", _settings.feedback_path),
        dsn=os.getenv("POSTGRES_DSN", _settings.postgres_dsn),
    )
    app.state.graph_store = InMemoryGraphStore()
    app.state.graph_store.seed_default()
    app.state.approval_queue = GraphApprovalQueue(
        path=os.getenv("GRAPH_APPROVAL_PATH", "./data/graph/approvals.jsonl")
    )
    app.state.gated_writer = GatedGraphWriter(app.state.graph_store, app.state.approval_queue)
    yield


app = FastAPI(title="expert-console-api", version="0.2.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "expert-console-api", "version": "0.2.0"}


# --- Answer review queue ---


@app.get("/v1/reviews")
async def list_reviews(status: str = "pending"):
    return [r for r in app.state.review_queue if r.get("status") == status]


@app.post("/v1/reviews")
async def enqueue_review(item: ReviewItem):
    data = item.model_dump()
    app.state.review_queue.append(data)
    return data


@app.post("/v1/reviews/decide")
async def decide(d: Decision):
    for r in app.state.review_queue:
        if r["item_id"] == d.item_id:
            r["status"] = d.decision
            r["notes"] = d.notes
            r["reviewed_by"] = d.reviewed_by
            return r
    raise HTTPException(status_code=404, detail="review not found")


# --- Flywheel feedback (shared store) ---


@app.get("/v1/feedback")
async def list_feedback(feedback_type: str | None = None, limit: int = 50):
    events = app.state.feedback.list(feedback_type=feedback_type, limit=limit)
    return {"count": len(events), "events": [e.to_dict() for e in events]}


@app.get("/v1/feedback/stats")
async def feedback_stats():
    return {"counts": app.state.feedback.count_by_type()}


@app.post("/v1/feedback/correction")
async def expert_correction(body: ExpertCorrection):
    event = FeedbackEvent(
        feedback_type=FeedbackType.EXPERT_CORRECTION.value,
        query_id=body.query_id,
        user_id=body.expert_id,
        query_text=body.query_text,
        answer_text=body.corrected_answer[:2000],
        reason=body.reason or "expert_correction",
        metadata={"original_answer": body.original_answer[:2000]},
    )
    app.state.feedback.append(event)
    return {"status": "ok", "event": event.to_dict()}


# --- E2 graph approval ---


@app.post("/v1/graph/propose/node")
async def propose_node(node: GraphNodeProposal):
    result = app.state.gated_writer.write_node(
        node.model_dump(exclude={"submitted_by"}),
        submitted_by=node.submitted_by,
    )
    return result


@app.post("/v1/graph/propose/edge")
async def propose_edge(edge: GraphEdgeProposal):
    result = app.state.gated_writer.write_edge(
        edge.model_dump(exclude={"submitted_by"}),
        submitted_by=edge.submitted_by,
    )
    return result


@app.get("/v1/graph/proposals")
async def list_proposals(status: str = "pending"):
    items = app.state.approval_queue.list(status=status or None)
    return {"count": len(items), "proposals": [p.to_dict() for p in items]}


@app.post("/v1/graph/proposals/decide")
async def decide_graph(d: GraphDecision):
    try:
        prop = app.state.approval_queue.decide(
            d.proposal_id,
            d.decision,
            reviewed_by=d.reviewed_by,
            notes=d.notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    applied = None
    if d.apply and prop.status == "approved":
        # mark payload approved then apply
        prop.payload["is_approved"] = True
        applied = app.state.approval_queue.apply_approved(
            app.state.graph_store, d.proposal_id
        )
    return {"proposal": prop.to_dict(), "applied": applied}


@app.get("/v1/graph/stats")
async def graph_stats():
    return {
        "nodes": app.state.graph_store.count_nodes(),
        "pending_proposals": len(app.state.approval_queue.list(status="pending")),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8009)
