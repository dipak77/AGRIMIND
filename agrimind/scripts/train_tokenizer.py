#!/usr/bin/env python3
"""CLI script to train a subword tokenizer (P0.1)."""

import argparse
import sys
from pathlib import Path

# Add workspace paths
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "models"))

from tokenizer.train import train_tokenizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Train KrishiMini Tokenizer")
    parser.add_argument("--corpus-file", type=str, help="Path to input text file")
    parser.add_argument("--vocab-size", type=int, default=16000, help="Target vocabulary size")
    parser.add_argument("--tokenizer-id", type=str, default="krishimini-tokenizer-16k", help="Tokenizer ID")
    parser.add_argument("--output-dir", type=str, default="runs/tokenizer", help="Output directory")

    args = parser.parse_args()

    sample_texts = [
        "Wheat sowing requires 50 kg nitrogen and 20 kg phosphorus per hectare in rabiseason.",
        "गेहूं की बुवाई के लिए 50 किलोग्राम नाइट्रोजन और 20 किलोग्राम फास्फोरस प्रति हेक्टेयर चाहिए।",
        "कापूस पिकासाठी योग्य प्रमाणात खत व पाणी देणे आवश्यक आहे.",
    ]
    if args.corpus_file and Path(args.corpus_file).is_file():
        corpus = Path(args.corpus_file).read_text(encoding="utf-8").splitlines()
    else:
        corpus = sample_texts

    model, manifest, data = train_tokenizer(
        corpus_texts=corpus,
        target_vocab_size=args.vocab_size,
        tokenizer_id=args.tokenizer_id,
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest.save(out_dir / f"{args.tokenizer_id}.json")
    (out_dir / f"{args.tokenizer_id}.blob").write_bytes(data)

    print(f"Successfully trained tokenizer {manifest.tokenizer_id} (vocab={manifest.vocab_size})")
    print(f"Manifest written to: {out_dir / f'{args.tokenizer_id}.json'}")


if __name__ == "__main__":
    main()
