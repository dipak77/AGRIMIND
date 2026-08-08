"""SLO budgets and latency helpers (Phase F3)."""

from __future__ import annotations

import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Sequence


# Plan-aligned defaults (ms)
SLO_CHAT_P95_MS = 2000.0  # end-to-end chat (local/dev budget)
SLO_RETRIEVAL_P95_MS = 300.0  # Phase 5 retrieval p95
SLO_INFERENCE_P95_MS = 1500.0
SLO_INGEST_P95_MS = 5000.0
SLO_ERROR_RATE_MAX = 0.01  # 1%


@dataclass(frozen=True)
class SLOBudget:
    name: str
    p95_ms: float
    p99_ms: float | None = None
    max_error_rate: float = SLO_ERROR_RATE_MAX


DEFAULT_SLOS: dict[str, SLOBudget] = {
    "chat": SLOBudget("chat", p95_ms=SLO_CHAT_P95_MS),
    "retrieval": SLOBudget("retrieval", p95_ms=SLO_RETRIEVAL_P95_MS),
    "inference": SLOBudget("inference", p95_ms=SLO_INFERENCE_P95_MS),
    "ingest": SLOBudget("ingest", p95_ms=SLO_INGEST_P95_MS),
    # Offline local-sync agent path (no HTTP). Keep tight for CI.
    "agent_local": SLOBudget("agent_local", p95_ms=2000.0),
}


@dataclass
class LoadResult:
    name: str
    n: int
    successes: int
    failures: int
    latencies_ms: list[float]
    p50_ms: float
    p95_ms: float
    p99_ms: float
    error_rate: float
    budget: SLOBudget | None = None
    budget_ok: bool = True
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "n": self.n,
            "successes": self.successes,
            "failures": self.failures,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "error_rate": self.error_rate,
            "budget_p95_ms": self.budget.p95_ms if self.budget else None,
            "budget_ok": self.budget_ok,
            "notes": self.notes,
        }


def percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return ordered[int(k)]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def run_load(
    fn: Callable[[], None],
    *,
    name: str = "load",
    n: int = 50,
    concurrency: int = 8,
    budget: SLOBudget | None = None,
) -> LoadResult:
    """
    Execute fn n times with thread pool; collect latency and errors.
    fn should raise on failure.
    """
    latencies: list[float] = []
    failures = 0

    def _one() -> float:
        start = time.perf_counter()
        fn()
        return (time.perf_counter() - start) * 1000.0

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(_one) for _ in range(n)]
        for fut in as_completed(futures):
            try:
                latencies.append(fut.result())
            except Exception:
                failures += 1

    successes = len(latencies)
    total = successes + failures
    err = failures / total if total else 1.0
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    budget_ok = True
    notes = ""
    if budget:
        if p95 > budget.p95_ms:
            budget_ok = False
            notes = f"p95 {p95:.1f}ms exceeds budget {budget.p95_ms}ms"
        if err > budget.max_error_rate:
            budget_ok = False
            notes = (notes + "; " if notes else "") + f"error_rate {err:.3f} > {budget.max_error_rate}"
    return LoadResult(
        name=name,
        n=total,
        successes=successes,
        failures=failures,
        latencies_ms=latencies,
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
        error_rate=err,
        budget=budget,
        budget_ok=budget_ok,
        notes=notes,
    )


def assert_slo(result: LoadResult) -> None:
    if not result.budget_ok:
        raise AssertionError(
            f"SLO failed for {result.name}: p95={result.p95_ms:.1f}ms "
            f"errors={result.error_rate:.3f} ({result.notes})"
        )
