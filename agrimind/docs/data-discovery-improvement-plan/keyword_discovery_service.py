"""
Plan-folder mirror of production multilingual keyword discovery.

CANONICAL IMPLEMENTATION:
  packages/data_kernel/data_kernel/sources/keyword_discovery_service.py

Re-exports production AutoSourceDiscoveryService (EN/HI/MR), search adapters,
and optional create_discovery_app() FastAPI factory.
"""

from __future__ import annotations

from data_kernel.sources.keyword_discovery_service import (  # noqa: F401
    AGRI_KEYWORD_MAP,
    ArchiveOrgSearch,
    AutoSourceDiscoveryService,
    FAOSearch,
    OpenLibrarySearch,
    WikipediaSearch,
    create_discovery_app,
    discover_multilingual,
    expand_keywords,
)

# Plan samples used relative import style: from .discovery import ...
# Prefer production package imports in new code.

__all__ = [
    "AGRI_KEYWORD_MAP",
    "ArchiveOrgSearch",
    "AutoSourceDiscoveryService",
    "FAOSearch",
    "OpenLibrarySearch",
    "WikipediaSearch",
    "create_discovery_app",
    "discover_multilingual",
    "expand_keywords",
]


if __name__ == "__main__":
    import json

    exp = expand_keywords(["cotton", "soil health", "irrigation"], ["en", "hi", "mr"])
    print("expanded:")
    print(json.dumps(exp, ensure_ascii=False, indent=2))

    svc = AutoSourceDiscoveryService(check_access=False)
    hits = svc.discover_by_keywords(
        keywords=["soil health", "cotton"],
        languages=["en", "hi", "mr"],
        max_total=12,
    )
    print(f"\ndiscovered={len(hits)}")
    for h in hits[:12]:
        print(
            f"  [{h.language}] trust={h.trust_score:3d} {h.source_type:10s} "
            f"| {h.provider:16s} | {h.title}"
        )
