#!/usr/bin/env python3
"""CLI script to benchmark tokenizer candidates (12K, 16K, 24K) (P0.1)."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "models"))

from tokenizer.evaluate import benchmark_tokenizer
from tokenizer.train import train_tokenizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Tokenizer Candidates")
    parser.add_argument("--candidates", nargs="+", type=int, default=[12000, 16000, 24000])
    args = parser.parse_args()

    sample_corpus = [
        "Wheat, rice, cotton and maize cultivation recommendations for Maharashtra and Madhya Pradesh.",
        "गेहूं, धान, कपास और मक्का की खेती के लिए कृषि विज्ञान केंद्र की सलाह।",
        "कापूस आणि सोयाबीन पिकांवरील किडींचे नियंत्रण करण्यासाठी उपाय.",
    ]

    reports = []
    for sz in args.candidates:
        tok, manifest, data = train_tokenizer(sample_corpus, target_vocab_size=sz, tokenizer_id=f"cand-{sz}")
        rep = benchmark_tokenizer(f"cand-{sz}", sz, tok.encode)
        reports.append(rep.to_dict())

    print("=== Tokenizer Benchmark Results ===")
    print(json.dumps(reports, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
