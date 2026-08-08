"""
Plan-folder mirror of production discovery (kept in sync).

CANONICAL IMPLEMENTATION:
  packages/data_kernel/data_kernel/sources/discovery.py

This module re-exports production symbols so older imports / plan samples
continue to work without duplicating logic.
"""

from __future__ import annotations

from data_kernel.sources.discovery import (  # noqa: F401
    DEFAULT_ALLOW_LIST,
    LICENSE_BY_DOMAIN,
    TRUST_SCORE,
    AccessCheckResult,
    DiscoveredSource,
    check_robots_txt,
    check_url_access_sync,
    default_seed_catalog,
    discover_sources,
    infer_license,
    infer_provider,
    infer_trust_score,
    is_url_allow_listed,
    normalize_license,
    real_source_catalog,
)

__all__ = [
    "DEFAULT_ALLOW_LIST",
    "LICENSE_BY_DOMAIN",
    "TRUST_SCORE",
    "AccessCheckResult",
    "DiscoveredSource",
    "check_robots_txt",
    "check_url_access_sync",
    "default_seed_catalog",
    "discover_sources",
    "infer_license",
    "infer_provider",
    "infer_trust_score",
    "is_url_allow_listed",
    "normalize_license",
    "real_source_catalog",
]


if __name__ == "__main__":
    seed = default_seed_catalog()
    print(f"allow_list={len(DEFAULT_ALLOW_LIST)} seed={len(seed)}")
    langs = {}
    for s in seed:
        langs[s.get("language", "?")] = langs.get(s.get("language", "?"), 0) + 1
    print("seed_by_lang:", langs)
    sample = discover_sources(seed[:5], check_access=False)
    for d in sample:
        print(f"  [{d.language}] trust={d.trust_score} allowed={d.allowed} {d.title}")
