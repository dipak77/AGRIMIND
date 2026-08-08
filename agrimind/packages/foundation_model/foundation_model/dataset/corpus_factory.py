"""Corpus Factory converting raw/curated data into tokenized shards & dataset products (P0.7)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence

from foundation_model.dataset.manifest import DatasetManifest
from foundation_model.dataset.split_engine import AntiContaminationSplitter, DocumentRecord


class CorpusFactory:
    """Consumes curated documents and generates immutable tokenized dataset products."""

    def __init__(
        self,
        tokenizer_fn: Callable[[str], List[int]],
        tokenizer_manifest_id: str = "krishimini-tokenizer-16k",
        dataset_product_type: str = "foundation_pretraining",
    ) -> None:
        self.tokenizer_fn = tokenizer_fn
        self.tokenizer_manifest_id = tokenizer_manifest_id
        self.dataset_product_type = dataset_product_type
        self.splitter = AntiContaminationSplitter()

    def build_dataset_product(
        self,
        documents: Sequence[DocumentRecord],
        output_dir: str | Path,
        dataset_id: str = "ds-krishimini-v1",
    ) -> tuple[DatasetManifest, Dict[str, Any]]:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        splits = self.splitter.split_corpus(documents)
        shard_hashes: List[str] = []
        total_tokens = 0
        lang_distribution: Dict[str, int] = {}

        stats: Dict[str, Any] = {
            "dataset_id": dataset_id,
            "product_type": self.dataset_product_type,
            "split_counts": {},
            "split_tokens": {},
        }

        for split_name, split_docs in splits.items():
            split_dir = out_path / split_name
            split_dir.mkdir(parents=True, exist_ok=True)

            token_shards: List[int] = []
            for doc in split_docs:
                tokens = self.tokenizer_fn(doc.text)
                token_shards.extend(tokens)
                lang_distribution[doc.language] = lang_distribution.get(doc.language, 0) + len(tokens)

            shard_file = split_dir / "shard_000.json"
            shard_data = {
                "tokens": token_shards,
                "doc_count": len(split_docs),
            }
            raw_bytes = json.dumps(shard_data).encode("utf-8")
            shard_file.write_bytes(raw_bytes)

            h = hashlib.sha256(raw_bytes).hexdigest()
            shard_hashes.append(h)

            total_tokens += len(token_shards)
            stats["split_counts"][split_name] = len(split_docs)
            stats["split_tokens"][split_name] = len(token_shards)

        combined_hash = hashlib.sha256("".join(shard_hashes).encode("utf-8")).hexdigest()

        manifest = DatasetManifest(
            dataset_id=dataset_id,
            dataset_product_type=self.dataset_product_type,
            tokenizer_manifest_id=self.tokenizer_manifest_id,
            languages=list(lang_distribution.keys()),
            token_count=total_tokens,
            document_count=len(documents),
            shards_count=len(shard_hashes),
            hash=combined_hash,
            metadata={"language_token_distribution": lang_distribution},
        )

        manifest.save(out_path / "manifest.json")
        with open(out_path / "statistics.json", "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)

        return manifest, stats
