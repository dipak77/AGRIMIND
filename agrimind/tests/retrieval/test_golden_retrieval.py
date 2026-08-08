"""B4: golden retrieval fixtures + offline harness (in-memory graph + fake vector)."""

from __future__ import annotations

import json
import pathlib

from eval.harness.retrieval_run import (
    DEFAULT_P95_BUDGET_MS,
    build_retriever,
    load_cases,
    resolve_dataset_dir,
    run,
)

GOLDEN_DIR = resolve_dataset_dir("packages/eval/golden/retrieval")


def test_golden_fixtures_exist_and_schema():
    cases = load_cases(GOLDEN_DIR)
    assert len(cases) >= 5, f"expected >=5 golden retrieval fixtures, got {len(cases)}"
    required = {
        "id",
        "lang",
        "query",
        "mode",
        "must_have_graph_path",
        "must_have_citations",
        "forbidden_terms",
        "min_confidence",
        "max_confidence",
        "p95_latency_ms_budget",
    }
    for case in cases:
        missing = required - set(case.keys())
        assert not missing, f"{case.get('id')}: missing keys {missing}"
        assert case["p95_latency_ms_budget"] == DEFAULT_P95_BUDGET_MS or case[
            "p95_latency_ms_budget"
        ] == int(DEFAULT_P95_BUDGET_MS)
        assert case["query"]
        assert case["mode"] in ("hybrid", "graph", "vector", "auto")


def test_golden_covers_required_scenarios():
    cases = load_cases(GOLDEN_DIR)
    ids = {c["id"] for c in cases}
    queries = " ".join(c["query"] for c in cases).lower()
    # cotton bollworm / IPM multi-hop
    assert any("bollworm" in c["query"].lower() and "ipm" in c["query"].lower() for c in cases)
    # crop rotation
    assert any("rotation" in c["query"].lower() for c in cases)
    # banned chemical forbidden terms present in at least one case
    assert any(
        "monocrotophos" in [t.lower() for t in (c.get("forbidden_terms") or [])] for c in cases
    )
    # market / scheme keyword
    assert any("scheme" in c["query"].lower() or "pm-kisan" in c["query"].lower() for c in cases)
    # multilingual token
    multi = any(
        any(tok in c["query"] for tok in ("कपास", "बोंडअळी", "हवामान")) for c in cases
    )
    assert multi, f"expected multilingual golden case among {ids}"
    assert "ret_en_cotton_bollworm_001" in ids or any("cotton" in q for q in queries.split())


def test_p95_budget_documented():
    assert DEFAULT_P95_BUDGET_MS == 300.0
    cases = load_cases(GOLDEN_DIR)
    for case in cases:
        assert "p95_latency_ms_budget" in case
        assert float(case["p95_latency_ms_budget"]) == 300.0


def test_build_retriever_offline_fixture():
    r = build_retriever(backend="fixture")
    assert r.backend == "live"
    health = r.health()
    assert health.get("graph_nodes", 0) >= 5
    # fake store has seeded docs
    assert r.store.count() >= 1


def test_all_golden_cases_pass_offline():
    report = run(
        dataset=str(GOLDEN_DIR),
        budget_ms=DEFAULT_P95_BUDGET_MS,
        skip_latency=False,
        backend="fixture",
        quiet=True,
    )
    failed = [c for c in report.case_results if not c["ok"]]
    assert not failed, f"golden cases failed: {failed}"
    assert report.passed == report.total >= 5
    assert report.p95_ms <= DEFAULT_P95_BUDGET_MS, (
        f"p95 {report.p95_ms:.1f}ms > budget {DEFAULT_P95_BUDGET_MS}ms"
    )
    assert report.all_ok


def test_harness_skip_latency_flag():
    report = run(
        dataset=str(GOLDEN_DIR),
        budget_ms=0.0,  # impossible budget
        skip_latency=True,
        backend="fixture",
        quiet=True,
    )
    assert report.failed == 0
    assert report.latency_ok is True
    assert report.all_ok is True


def test_fixture_files_are_valid_json():
    for path in sorted(pathlib.Path(GOLDEN_DIR).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["id"] in path.name or path.stem.startswith("ret_")
