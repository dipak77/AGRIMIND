"""
Golden retrieval evaluation harness (B4).

Runs HybridRetriever against offline fixtures:
  - InMemoryGraphStore (seeded default Crop–Pest–Practice graph)
  - Fake in-memory vector store + LocalHashEmbedder (no Qdrant/Neo4j/Redis)

Latency SLO (Phase 5 / plan Phase B B4):
  p95 query latency budget defaults to **300ms** for the offline fixture path.
  Documented target remains 300ms; production live path may differ.

Usage:
  python -m eval.harness.retrieval_run --dataset packages/eval/golden/retrieval --budget-ms 300
  python -m eval.harness.retrieval_run --skip-latency   # cases only, ignore p95
  make eval-retrieval

Exit code 0 only if all golden cases pass and (unless --skip-latency) p95 <= budget.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from memory.graph.neo4j_store import InMemoryGraphStore
from memory.retrieval.service import HybridRetriever, RetrievalRequest, RetrievalResult
from memory.vector.embedder import LocalHashEmbedder, cosine_similarity
from memory.vector.qdrant_store import ScoredPoint, VectorPoint
from memory.vector.seed_corpus import default_seed_documents

# Default p95 latency budget from original plan Phase 5 / B4 (milliseconds).
DEFAULT_P95_BUDGET_MS = 300.0


@dataclass
class FakeQdrantStore:
    """Minimal in-memory stand-in for QdrantStore (offline golden harness)."""

    url: str = "fake://qdrant"
    collection: str = "agrimind_chunks"
    dimension: int = 64
    points: dict[str, VectorPoint] = field(default_factory=dict)

    def ping(self) -> bool:
        return True

    def ensure_collection(self) -> None:
        return None

    def upsert(self, points: list[VectorPoint]) -> int:
        for p in points:
            self.points[p.id] = p
        return len(points)

    def search(
        self,
        vector: list[float],
        top_k: int = 8,
        score_threshold: float | None = 0.0,
        filters: dict[str, Any] | None = None,
    ) -> list[ScoredPoint]:
        scored: list[ScoredPoint] = []
        for p in self.points.values():
            if filters and any(p.payload.get(k) != v for k, v in filters.items()):
                continue
            score = cosine_similarity(vector, p.vector)
            if score_threshold is not None and score < score_threshold:
                continue
            scored.append(ScoredPoint(id=p.id, score=score, payload=dict(p.payload)))
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def count(self) -> int:
        return len(self.points)


def resolve_dataset_dir(dataset: str) -> pathlib.Path:
    p = pathlib.Path(dataset)
    if p.exists():
        return p
    # package-relative: packages/eval/golden/retrieval
    here = pathlib.Path(__file__).resolve()
    candidates = [
        here.parents[2] / "golden" / "retrieval",  # packages/eval/golden/retrieval
        pathlib.Path.cwd() / "packages" / "eval" / "golden" / "retrieval",
        pathlib.Path.cwd() / dataset,
    ]
    for c in candidates:
        if c.exists():
            return c
    return p


def load_cases(dataset_dir: pathlib.Path) -> list[dict[str, Any]]:
    files = sorted(dataset_dir.glob("*.json"))
    cases: list[dict[str, Any]] = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        data["_fixture_path"] = str(f)
        cases.append(data)
    return cases


def build_retriever(backend: str = "fixture") -> HybridRetriever:
    """
    Offline retriever: live HybridRetriever API with injected in-memory graph + fake Qdrant.

    backend:
      - fixture / live: InMemoryGraphStore + FakeQdrantStore + seed corpus (recommended)
      - stub: HybridRetriever(backend="stub") with seeded in-memory graph only
    """
    if backend == "stub":
        return HybridRetriever(backend="stub")

    emb = LocalHashEmbedder(dimension=64)
    store = FakeQdrantStore(dimension=64)
    graph = InMemoryGraphStore()
    graph.seed_default()
    retriever = HybridRetriever(
        backend="live",
        store=store,  # type: ignore[arg-type]
        embedder=emb,
        graph_store=graph,
        vector_enabled=True,
        graph_enabled=True,
    )
    retriever.upsert_documents(default_seed_documents())
    return retriever


def _path_blob(result: RetrievalResult) -> str:
    parts: list[str] = []
    for p in result.graph_paths:
        parts.append(p.summary or "")
        for n in p.nodes:
            parts.append(str(n.get("name") or ""))
            parts.append(str(n.get("id") or ""))
            parts.append(str(n.get("type") or ""))
    return " ".join(parts).lower()


def _path_node_names_blob(result: RetrievalResult) -> str:
    names: list[str] = []
    for p in result.graph_paths:
        for n in p.nodes:
            names.append(str(n.get("name") or ""))
            names.append(str(n.get("id") or ""))
    return " ".join(names).lower()


def _chunks_blob(result: RetrievalResult) -> str:
    parts: list[str] = []
    for c in result.chunks:
        parts.append(c.text or "")
        parts.append(c.content or "")
        parts.append(c.source_id or "")
    return " ".join(parts).lower()


def _has_citations(result: RetrievalResult) -> bool:
    if result.has_citations:
        return True
    if any(c.citation is not None or c.source_id for c in result.chunks):
        return True
    if any(bool(p.citations) for p in result.graph_paths):
        return True
    return False


def evaluate_case(case: dict[str, Any], result: RetrievalResult, latency_ms: float) -> list[str]:
    """Return list of failure reasons (empty => pass)."""
    reasons: list[str] = []
    cid = case.get("id", "?")

    if case.get("must_have_graph_path"):
        if not result.graph_paths:
            reasons.append(f"{cid}: must_have_graph_path but no graph_paths")

    path_blob = _path_blob(result)
    for needle in case.get("expected_path_contains") or []:
        if str(needle).lower() not in path_blob:
            reasons.append(f"{cid}: expected_path_contains missing '{needle}'")

    chunk_blob = _chunks_blob(result)
    for needle in case.get("expected_chunk_contains") or []:
        if str(needle).lower() not in chunk_blob:
            reasons.append(f"{cid}: expected_chunk_contains missing '{needle}'")

    if case.get("must_have_citations") and not _has_citations(result):
        reasons.append(f"{cid}: must_have_citations but none found")

    forbidden = case.get("forbidden_terms") or []
    forbidden_in = (case.get("forbidden_in") or "graph_path_nodes").lower()
    if forbidden:
        if forbidden_in in ("graph_path_nodes", "path_nodes", "nodes"):
            blob = _path_node_names_blob(result)
        elif forbidden_in in ("graph_path", "path", "paths"):
            blob = path_blob
        else:
            blob = path_blob + " " + chunk_blob
        for term in forbidden:
            if str(term).lower() in blob:
                reasons.append(f"{cid}: forbidden term '{term}' in {forbidden_in}")

    conf = float(result.confidence)
    min_c = float(case.get("min_confidence", 0.0))
    max_c = float(case.get("max_confidence", 1.0))
    if conf < min_c:
        reasons.append(f"{cid}: confidence {conf:.3f} < min {min_c}")
    if conf > max_c:
        reasons.append(f"{cid}: confidence {conf:.3f} > max {max_c}")

    # Per-case budget is informational; aggregate p95 checked in run()
    _ = latency_ms
    return reasons


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    # nearest-rank style for small N
    k = max(0, min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[k]


@dataclass
class RunReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    case_results: list[dict[str, Any]] = field(default_factory=list)
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    budget_ms: float = DEFAULT_P95_BUDGET_MS
    latency_ok: bool = True
    all_ok: bool = False


def run(
    dataset: str = "packages/eval/golden/retrieval",
    budget_ms: float = DEFAULT_P95_BUDGET_MS,
    skip_latency: bool = False,
    backend: str = "fixture",
    quiet: bool = False,
) -> RunReport:
    dataset_dir = resolve_dataset_dir(dataset)
    cases = load_cases(dataset_dir)
    report = RunReport(budget_ms=budget_ms)

    if not cases:
        if not quiet:
            print(f"FAIL no golden JSON files in {dataset_dir}")
        report.all_ok = False
        return report

    retriever = build_retriever(backend=backend)
    report.total = len(cases)

    for case in cases:
        cid = case.get("id") or pathlib.Path(case.get("_fixture_path", "case")).stem
        mode = case.get("mode") or "hybrid"
        query = case.get("query") or ""
        lang = case.get("lang") or "en"

        t0 = time.perf_counter()
        try:
            result = retriever.retrieve(
                RetrievalRequest(
                    query=query,
                    lang=lang,
                    mode=mode,
                    top_k=8,
                    require_citations=bool(case.get("must_have_citations", True)),
                )
            )
            err = None
        except Exception as exc:  # pragma: no cover - defensive
            result = None
            err = str(exc)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        report.latencies_ms.append(latency_ms)

        if err or result is None:
            reasons = [f"{cid}: retrieve error: {err}"]
        else:
            reasons = evaluate_case(case, result, latency_ms)

        ok = not reasons
        if ok:
            report.passed += 1
            if not quiet:
                conf = result.confidence if result else 0.0
                n_paths = len(result.graph_paths) if result else 0
                n_chunks = len(result.chunks) if result else 0
                print(
                    f"PASS {cid} conf={conf:.3f} paths={n_paths} "
                    f"chunks={n_chunks} latency_ms={latency_ms:.1f}"
                )
        else:
            report.failed += 1
            if not quiet:
                print(f"FAIL {cid} latency_ms={latency_ms:.1f}: {reasons}")

        report.case_results.append(
            {
                "id": cid,
                "ok": ok,
                "latency_ms": latency_ms,
                "reasons": reasons,
                "confidence": float(result.confidence) if result else None,
            }
        )

    report.p50_ms = percentile(report.latencies_ms, 50)
    report.p95_ms = percentile(report.latencies_ms, 95)
    # Also compute true-ish p95 via statistics when enough samples
    if len(report.latencies_ms) >= 2:
        try:
            report.p95_ms = float(
                statistics.quantiles(report.latencies_ms, n=20, method="inclusive")[18]
            )
        except Exception:
            pass

    report.latency_ok = skip_latency or (report.p95_ms <= budget_ms)
    cases_ok = report.failed == 0 and report.total > 0
    report.all_ok = cases_ok and report.latency_ok

    if not quiet:
        print(
            f"Summary: {report.passed}/{report.total} cases passed | "
            f"p50={report.p50_ms:.1f}ms p95={report.p95_ms:.1f}ms "
            f"budget={budget_ms:.0f}ms "
            f"{'SKIP_LATENCY' if skip_latency else ('OK' if report.latency_ok else 'OVER_BUDGET')}"
        )
        if not report.latency_ok:
            print(
                f"FAIL p95 latency {report.p95_ms:.1f}ms exceeds budget {budget_ms:.0f}ms "
                f"(use --skip-latency to ignore)"
            )
        print(f"Overall: {'PASS' if report.all_ok else 'FAIL'}")

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AGRIMIND golden retrieval harness (B4)")
    parser.add_argument(
        "--dataset",
        default="packages/eval/golden/retrieval",
        help="Directory of golden retrieval JSON fixtures",
    )
    parser.add_argument(
        "--budget-ms",
        type=float,
        default=DEFAULT_P95_BUDGET_MS,
        help=f"p95 latency budget in ms (default {DEFAULT_P95_BUDGET_MS:.0f})",
    )
    parser.add_argument(
        "--skip-latency",
        action="store_true",
        help="Do not fail when p95 exceeds budget",
    )
    parser.add_argument(
        "--backend",
        choices=("fixture", "live", "stub"),
        default="fixture",
        help="fixture/live = in-memory graph + fake vector; stub = HybridRetriever stub",
    )
    args = parser.parse_args(argv)
    backend = "fixture" if args.backend == "live" else args.backend
    report = run(
        dataset=args.dataset,
        budget_ms=args.budget_ms,
        skip_latency=args.skip_latency,
        backend=backend,
    )
    return 0 if report.all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
