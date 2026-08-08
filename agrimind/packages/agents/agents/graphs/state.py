"""Agent graph state (LangGraph-compatible TypedDict; sequential runner for now)."""

from __future__ import annotations

from typing import Any, TypedDict

from agrimind_kernel.contracts import Citation, Query


class AgentState(TypedDict, total=False):
    query: Query
    intent: str
    retrieval_results: Any
    tool_outputs: dict[str, Any]
    draft_answer: str
    safety_flags: list[str]
    confidence: float
    citations: list[Citation]
    final_answer: str
    model_version: str
    safety_level: str
    action: str
    fallback_used: bool
    requires_review: bool
    trace_id: str
