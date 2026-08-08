"""Phase E: feedback flywheel, graph approval, canary rollback."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "packages" / "models"
MEMORY = ROOT / "packages" / "memory"
for p in (MODELS, MEMORY):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from agrimind_kernel.feedback.events import (
    FeedbackEvent,
    FeedbackType,
    InMemoryFeedbackStore,
    capture_response_signals,
)
from memory.graph.approval import (
    GatedGraphWriter,
    GraphApprovalQueue,
    is_high_risk_node,
)
from memory.graph.neo4j_store import InMemoryGraphStore
from registry.canary import CanaryController
from registry.client import ModelRegistryClient
from registry.gates import GateError
from registry.schemas import EvalScores


def test_thumbs_and_low_confidence_capture():
    store = InMemoryFeedbackStore()
    store.append(
        FeedbackEvent(
            feedback_type=FeedbackType.THUMBS_DOWN.value,
            query_text="pest spray?",
            answer_text="use IPM",
            reason="thumbs_down",
        )
    )
    emitted = capture_response_signals(
        store,
        query_id="q1",
        user_id="u1",
        query_text="dosage?",
        answer_text="fallback",
        confidence=0.3,
        intent="chemical_dosage",
        model_version="m1",
        trace_id="t1",
        fallback_used=True,
        requires_review=True,
    )
    assert len(emitted) >= 1
    types = {e.feedback_type for e in store.list(limit=20)}
    assert FeedbackType.THUMBS_DOWN.value in types
    assert FeedbackType.LOW_CONFIDENCE.value in types
    assert FeedbackType.SAFETY_FALLBACK.value in types
    assert store.count_by_type()[FeedbackType.THUMBS_DOWN.value] == 1


def test_high_risk_chemical_node_requires_approval():
    assert is_high_risk_node({"type": "Chemical", "name": "X"}) is True
    g = InMemoryGraphStore()
    g.seed_default()
    q = GraphApprovalQueue()
    writer = GatedGraphWriter(g, q)
    result = writer.write_node(
        {
            "id": "chemical:newchem",
            "type": "Chemical",
            "name": "NewChem",
            "is_approved": False,
            "safety_critical": True,
        },
        submitted_by="pipeline",
    )
    assert result["written"] is False
    assert result["status"] == "pending"
    prop = result["proposal"]
    # expert approves + apply
    decided = q.decide(prop["proposal_id"], "approved", reviewed_by="agronomist")
    assert decided.status == "approved"
    decided.payload["is_approved"] = True
    applied = q.apply_approved(g, prop["proposal_id"])
    assert applied["count"] == 1
    assert "chemical:newchem" in g.nodes


def test_low_risk_practice_writes_directly():
    g = InMemoryGraphStore()
    q = GraphApprovalQueue()
    writer = GatedGraphWriter(g, q)
    result = writer.write_node(
        {
            "id": "practice:mulch",
            "type": "Practice",
            "name": "Mulching",
            "is_approved": True,
        }
    )
    assert result["written"] is True
    assert g.nodes["practice:mulch"]["name"] == "Mulching"


def test_canary_rollback_on_regression(tmp_path: Path):
    reg = ModelRegistryClient(tmp_path / "reg")
    reg.ensure_seed_defaults()
    ctrl = CanaryController(reg, state_path=tmp_path / "canary.json")
    ctrl.set_production("agrimind-7b-sim-v0.1.0")
    # bad model cannot start canary
    with pytest.raises(GateError):
        ctrl.start_canary("agrimind-7b-bad-v0.0.1", traffic_pct=20)
    # use good model as canary (same as prod for unit simplicity — promote edge)
    # edge model also promotable
    ctrl.start_canary("agrimind-18m-sim-v0.1.0", traffic_pct=20)
    assert ctrl.state.canary_model_id == "agrimind-18m-sim-v0.1.0"
    # regression → rollback
    result = ctrl.evaluate_canary_and_maybe_rollback(
        EvalScores(faithfulness=0.40, safety=0.5),
        production_scores=EvalScores(faithfulness=0.96, safety=1.0),
    )
    assert result.rolled_back is True
    assert ctrl.state.canary_model_id is None
    assert ctrl.state.production_model_id == "agrimind-7b-sim-v0.1.0"


def test_canary_traffic_split(tmp_path: Path):
    reg = ModelRegistryClient(tmp_path / "reg")
    reg.ensure_seed_defaults()
    ctrl = CanaryController(reg, state_path=tmp_path / "canary.json")
    ctrl.set_production("agrimind-7b-sim-v0.1.0")
    ctrl.start_canary("agrimind-18m-sim-v0.1.0", traffic_pct=50)
    # deterministic rand_pct
    assert ctrl.choose_model("default", rand_pct=10) == "agrimind-18m-sim-v0.1.0"
    assert ctrl.choose_model("default", rand_pct=90) == "agrimind-7b-sim-v0.1.0"
