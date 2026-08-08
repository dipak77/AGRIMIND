"""Group-level Anti-Contamination Dataset Split Engine (P0.8)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple


@dataclass
class DocumentRecord:
    document_id: str
    text: str
    language: str
    document_group_id: str | None = None
    translation_group_id: str | None = None
    source_family_id: str | None = None
    semantic_cluster_id: str | None = None


class AntiContaminationSplitter:
    """Assigns documents to train/val/test splits strictly at the group level."""

    def __init__(
        self,
        train_ratio: float = 0.85,
        val_ratio: float = 0.10,
        test_ratio: float = 0.05,
        seed: int = 42,
    ) -> None:
        assert round(train_ratio + val_ratio + test_ratio, 4) == 1.0
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.seed = seed

    def _determine_group_key(self, doc: DocumentRecord) -> str:
        """Derive the group key prioritizing translation > document_group > source_family > doc_id."""
        return (
            doc.translation_group_id
            or doc.document_group_id
            or doc.semantic_cluster_id
            or doc.source_family_id
            or doc.document_id
        )

    def _hash_group_key(self, group_key: str) -> float:
        """Deterministic hash float in [0.0, 1.0)."""
        h = hashlib.sha256(f"{self.seed}:{group_key}".encode("utf-8")).hexdigest()
        val = int(h[:8], 16)
        return float(val) / float(0xFFFFFFFF)

    def assign_split(self, doc: DocumentRecord) -> str:
        group_key = self._determine_group_key(doc)
        hash_val = self._hash_group_key(group_key)

        if hash_val < self.train_ratio:
            return "train"
        elif hash_val < (self.train_ratio + self.val_ratio):
            return "validation"
        else:
            return "test"

    def split_corpus(
        self, docs: Sequence[DocumentRecord]
    ) -> Dict[str, List[DocumentRecord]]:
        splits: Dict[str, List[DocumentRecord]] = {
            "train": [],
            "validation": [],
            "test": [],
        }
        for doc in docs:
            target = self.assign_split(doc)
            splits[target].append(doc)
        return splits
