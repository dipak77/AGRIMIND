#!/usr/bin/env python3
"""CLI: multilingual agri source discovery (EN / HI / MR).

Uses production modules under packages/data_kernel.

Examples (from agrimind/):
  uv run python scripts/discover_agri_sources.py --keywords "cotton,soil health"
  uv run python scripts/discover_agri_sources.py -k "irrigation" --langs en,hi,mr --pdf-books
  uv run python scripts/discover_agri_sources.py -k "agriculture" --check-access --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AGRIMIND agri domain discovery (EN/HI/MR trusted open sources)"
    )
    parser.add_argument(
        "-k",
        "--keywords",
        default="agriculture,soil health",
        help="Comma-separated keywords (default: agriculture,soil health)",
    )
    parser.add_argument(
        "--langs",
        default="en,hi,mr",
        help="Comma-separated languages: en,hi,mr",
    )
    parser.add_argument(
        "--types",
        default="wikipedia,pdf,web",
        help="Source types: wikipedia,pdf,web",
    )
    parser.add_argument("--max", type=int, default=25, help="Max results")
    parser.add_argument(
        "--check-access",
        action="store_true",
        help="HEAD/GET access probe (slower)",
    )
    parser.add_argument(
        "--pdf-books",
        action="store_true",
        help="Also run PDF book finder for first keyword",
    )
    parser.add_argument(
        "--json",
        dest="json_out",
        default=None,
        help="Write full JSON results to path",
    )
    parser.add_argument(
        "--expand-only",
        action="store_true",
        help="Only print EN/HI/MR keyword expansion",
    )
    args = parser.parse_args(argv)

    from data_kernel.sources.keyword_discovery_service import (
        AutoSourceDiscoveryService,
        expand_keywords,
    )

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    langs = [x.strip() for x in args.langs.split(",") if x.strip()]
    types = [x.strip() for x in args.types.split(",") if x.strip()]

    expanded = expand_keywords(keywords, langs)
    print("=== Keyword expansion (EN/HI/MR) ===")
    for lang, kws in expanded.items():
        print(f"  {lang}: {', '.join(kws[:12])}")

    if args.expand_only:
        return 0

    svc = AutoSourceDiscoveryService(check_access=args.check_access)
    results = svc.discover_by_keywords(
        keywords=keywords,
        languages=langs,
        source_types=types,
        max_total=args.max,
    )

    print(f"\n=== Discovered {len(results)} allowed sources ===")
    by_lang: dict[str, int] = {}
    for r in results:
        by_lang[r.language] = by_lang.get(r.language, 0) + 1
        print(
            f"  [{r.language}] trust={r.trust_score:3d} {r.source_type:10s} "
            f"| {str(r.provider or ''):16s} | {r.title or r.source_url}"
        )
    print("by_language:", by_lang)

    books = []
    if args.pdf_books and keywords:
        books = svc.find_pdf_books(keywords[0], max_books=8)
        print(f"\n=== PDF books for '{keywords[0]}': {len(books)} ===")
        for b in books:
            print(f"  trust={b.trust_score} | {b.title} | {b.source_url[:70]}")

    if args.json_out:
        payload = {
            "keywords": keywords,
            "languages": langs,
            "expanded": expanded,
            "count": len(results),
            "sources": [r.to_dict() for r in results],
            "pdf_books": [b.to_dict() for b in books],
        }
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWrote {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
