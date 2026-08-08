"""Agent pipeline unit tests."""

from agents.graphs.orchestrator import run_agent, state_to_response
from agrimind_kernel.contracts import Language, Query


def test_run_agent_general():
    q = Query(text="What is crop rotation?", lang=Language.ENGLISH, user_id="t1")
    state = run_agent(q, trace_id="trace-1")
    assert state["final_answer"]
    assert state["intent"] == "general_advisory"
    assert state["confidence"] <= 0.9


def test_run_agent_blocks_banned():
    q = Query(text="Should I spray monocrotophos?", user_id="t1")
    state = run_agent(q)
    assert state.get("fallback_used") is True or "monocrotophos" not in state["final_answer"].lower()
    assert state["confidence"] < 0.5 or state.get("fallback_used")


def test_state_to_response():
    q = Query(text="Cotton bollworm treatment?", user_id="t1")
    state = run_agent(q)
    resp = state_to_response(state)
    assert resp.answer
    assert resp.trace_id
    assert resp.model_version
    assert "intent" in resp.metadata


def test_intent_market():
    q = Query(text="What is cotton market price in Pune?", user_id="t1")
    state = run_agent(q)
    assert state["intent"] == "market_price"
