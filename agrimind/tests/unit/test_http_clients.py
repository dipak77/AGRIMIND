"""Unit tests for memory/inference HTTP clients with local fallback."""

import pytest

from agents.clients.inference_client import InferenceClient, build_grounded_completion
from agents.clients.memory_client import MemoryClient
from agents.graphs.orchestrator import run_agent, run_agent_async
from agrimind_kernel.contracts import Language, Query


def test_build_grounded_completion():
    text = build_grounded_completion(
        prompt="q",
        model_id="m1",
        intent="general_advisory",
        lang="en",
        evidence="soil health tips",
    )
    assert "soil health tips" in text
    assert "sim-model:m1" in text


def test_memory_local_fallback():
    client = MemoryClient(base_url="http://127.0.0.1:9", allow_local_fallback=True)
    # will fail HTTP and fall back
    import asyncio

    result = asyncio.run(client.retrieve("cotton bollworm", lang="en"))
    assert result.get("_backend") == "local_fallback"
    assert result.get("chunks")
    citations = MemoryClient.parse_citations(result)
    assert citations


def test_inference_local_fallback():
    client = InferenceClient(base_url="http://127.0.0.1:9", allow_local_fallback=True)
    import asyncio

    result = asyncio.run(
        client.generate(
            "Farmer query about soil",
            intent="general_advisory",
            lang="en",
            evidence="rotate crops",
        )
    )
    assert result.get("_backend") == "local_fallback"
    assert "rotate crops" in result["completion"]


def test_memory_no_fallback_raises():
    client = MemoryClient(base_url="http://127.0.0.1:9", allow_local_fallback=False)
    import asyncio

    with pytest.raises(RuntimeError, match="memory-service"):
        asyncio.run(client.retrieve("x"))


def test_run_agent_async_local_fallback():
    q = Query(text="What is crop rotation?", lang=Language.ENGLISH, user_id="t")
    import asyncio

    state = asyncio.run(
        run_agent_async(
            q,
            trace_id="t-http",
            memory_url="http://127.0.0.1:9",
            inference_url="http://127.0.0.1:9",
            allow_local_fallback=True,
        )
    )
    assert state["final_answer"]
    assert state["intent"] == "general_advisory"
    backend = (state.get("retrieval_results") or {}).get("_backend")
    assert backend == "local_fallback"


def test_run_agent_sync_still_works():
    q = Query(text="cotton market price", user_id="t")
    state = run_agent(q)
    assert state["intent"] == "market_price"
    assert state["final_answer"]
