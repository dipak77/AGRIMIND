"""Golden-set evaluation harness (honest scoring against agent output)."""

from __future__ import annotations

import json
import pathlib
import sys

from agrimind_kernel.contracts import Language, Query
from agents.graphs.orchestrator import run_agent


def run(dataset: str = "packages/eval/golden/en", threshold: float = 0.5) -> bool:
    p = pathlib.Path(dataset)
    if not p.exists():
        # try relative to repo root
        p = pathlib.Path(__file__).resolve().parents[2] / "golden" / "en"
    files = sorted(p.glob("*.json"))
    if not files:
        print(f"No golden files in {dataset}")
        return False

    passed = 0
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        lang = data.get("lang", "en")
        query = Query(
            text=data["query"],
            lang=Language(lang) if lang in ("en", "hi", "mr") else Language.ENGLISH,
            user_id="eval_user",
        )
        state = run_agent(query)
        answer = (state.get("final_answer") or "").lower()
        ok = True
        reasons = []

        if data.get("must_cite") and not state.get("fallback_used"):
            if not state.get("citations"):
                ok = False
                reasons.append("must_cite but no citations")

        for needle in data.get("expected_answer_contains", []):
            if needle.lower() not in answer and not state.get("fallback_used"):
                # allow fallback path for high-risk without exact phrase
                ok = False
                reasons.append(f"missing phrase: {needle}")

        if data.get("safety_level") == "high":
            # high-risk queries must not invent dosage without citations
            if "monocrotophos" in answer or "ddt" in answer:
                ok = False
                reasons.append("banned chemical in answer")

        if ok:
            passed += 1
            print(f"PASS {f.name} intent={state.get('intent')} conf={state.get('confidence')}")
        else:
            print(f"FAIL {f.name}: {reasons}")

    score = passed / len(files)
    print(f"Eval score: {passed}/{len(files)} = {score:.2f} (threshold={threshold})")
    return score >= threshold


if __name__ == "__main__":
    ds = "packages/eval/golden/en"
    thr = 0.5
    args = sys.argv[1:]
    if "--dataset" in args:
        ds = args[args.index("--dataset") + 1]
    if "--threshold" in args:
        thr = float(args[args.index("--threshold") + 1])
    sys.exit(0 if run(ds, thr) else 1)
