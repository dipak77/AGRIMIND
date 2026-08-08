"""
Plan-folder mirror of production source connectors.

CANONICAL IMPLEMENTATION:
  packages/data_kernel/data_kernel/sources/connectors.py

Includes hardened PDF extraction (120 pages), HI/MR Wikipedia titles,
word_count / is_valid helpers.
"""

from __future__ import annotations

from data_kernel.sources.connectors import (  # noqa: F401
    FetchedSource,
    fetch_source,
)

__all__ = ["FetchedSource", "fetch_source"]


if __name__ == "__main__":
    # Offline inline smoke (no network)
    fs = fetch_source(
        "https://example.com/demo",
        "web",
        inline_content=(
            "ICAR soil health and cotton bollworm IPM advisory for farmers: "
            "fertilizer, irrigation, crop rotation practices."
        ),
    )
    print(f"valid={fs.is_valid()} words={fs.word_count()} type={fs.source_type}")
    print(fs.text[:120] if fs.text else "")
