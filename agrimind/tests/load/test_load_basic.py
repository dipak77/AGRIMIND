"""Load tests + SLO enforcement (Phase F3).

These run offline (no Docker). They measure p50/p95 for critical local paths
and assert plan budgets.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENV", "test")
os.environ.setdefault("JWT_SECRET", "local-dev-secret-key-min-32-chars-long!")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("MEMORY_BACKEND", "stub")

from agrimind_kernel.contracts import Language, Query
from agrimind_kernel.slo.budgets import DEFAULT_SLOS, assert_slo, run_load
from agents.graphs.orchestrator import _run_agent_sync_local
from memory.retrieval.service import HybridRetriever, RetrievalRequest


class TestLoadSLOs:
    def test_agent_local_p95_under_budget(self):
        def once():
            # Use local-sync path (no HTTP timeouts to missing services)
            state = _run_agent_sync_local(
                Query(text="Cotton bollworm treatment IPM?", lang=Language.ENGLISH, user_id="load")
            )
            assert state.get("final_answer")

        result = run_load(
            once,
            name="agent_local",
            n=20,
            concurrency=4,
            budget=DEFAULT_SLOS["agent_local"],
        )
        assert result.failures == 0
        assert_slo(result)
        assert result.p95_ms <= DEFAULT_SLOS["agent_local"].p95_ms

    def test_retrieval_p95_under_300ms(self):
        retriever = HybridRetriever(backend="stub")

        def once():
            res = retriever.retrieve(
                RetrievalRequest(query="crop rotation soil", lang="en", mode="hybrid")
            )
            assert res.confidence >= 0

        result = run_load(
            once,
            name="retrieval",
            n=40,
            concurrency=8,
            budget=DEFAULT_SLOS["retrieval"],
        )
        assert result.failures == 0
        assert_slo(result)
        # Plan Phase 5: retrieval p95 < 300ms
        assert result.p95_ms < 300.0

    def test_slo_report_fields(self):
        result = run_load(lambda: None, name="noop", n=10, concurrency=2, budget=DEFAULT_SLOS["chat"])
        d = result.to_dict()
        assert d["p50_ms"] >= 0
        assert d["p95_ms"] >= 0
        assert d["budget_ok"] is True
