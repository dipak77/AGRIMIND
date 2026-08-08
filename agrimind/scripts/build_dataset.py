#!/usr/bin/env python3
"""CLI script to build dataset products and tokenized shards (P0.7/P0.8)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "foundation_model"))

from foundation_model.dataset.corpus_factory import CorpusFactory
from foundation_model.dataset.split_engine import DocumentRecord


def simple_whitespace_tokenizer(text: str) -> list[int]:
    return [hash(w) % 16000 for w in text.split()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build KrishiMini Dataset Product")
    parser.add_argument("--dataset-id", type=str, default="ds-krishimini-v1")
    parser.add_argument("--product-type", type=str, default="foundation_pretraining")
    parser.add_argument("--output-dir", type=str, default="runs/dataset/ds-krishimini-v1")

    args = parser.parse_args()

    sample_docs = [
        DocumentRecord(
            document_id="doc-en-001",
            text="Wheat cultivation requires nitrogen fertilizer.",
            language="en",
            translation_group_id="trans-grp-1",
        ),
        DocumentRecord(
            document_id="doc-hi-001",
            text="गेहूं की खेती के लिए नाइट्रोजन उर्वरक की आवश्यकता होती है।",
            language="hi",
            translation_group_id="trans-grp-1",  # Same group as doc-en-001
        ),
        DocumentRecord(
            document_id="doc-mr-001",
            text="कापूस पिकासाठी योग्य प्रमाणात पाणी देणे आवश्यक आहे.",
            language="mr",
            document_group_id="doc-grp-2",
        ),
    ]

    factory = CorpusFactory(
        tokenizer_fn=simple_whitespace_tokenizer,
        dataset_product_type=args.product_type,
    )

    manifest, stats = factory.build_dataset_product(
        documents=sample_docs,
        output_dir=args.output_dir,
        dataset_id=args.dataset_id,
    )

    print(f"Successfully built dataset product: {manifest.dataset_id}")
    print(f"Total Documents: {manifest.document_count}")
    print(f"Total Tokens:    {manifest.token_count}")
    print(f"Manifest Hash:   {manifest.hash[:16]}...")
    print(f"Manifest saved:  {Path(args.output_dir) / 'manifest.json'}")


if __name__ == "__main__":
    main()
