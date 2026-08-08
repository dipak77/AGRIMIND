"""Flywheel feedback events — low confidence, thumbs, expert corrections (E1)."""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class FeedbackType(StrEnum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    LOW_CONFIDENCE = "low_confidence"
    SAFETY_FALLBACK = "safety_fallback"
    EXPERT_CORRECTION = "expert_correction"
    RETRIEVAL_MISS = "retrieval_miss"


@dataclass
class FeedbackEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    feedback_type: str = FeedbackType.THUMBS_DOWN.value
    query_id: str | None = None
    user_id: str | None = None
    query_text: str = ""
    answer_text: str = ""
    confidence: float | None = None
    intent: str | None = None
    model_version: str | None = None
    trace_id: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    tenant_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeedbackEvent":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


class FeedbackStore(Protocol):
    def append(self, event: FeedbackEvent) -> FeedbackEvent: ...
    def list(
        self,
        *,
        feedback_type: str | None = None,
        limit: int = 100,
    ) -> list[FeedbackEvent]: ...
    def count_by_type(self) -> dict[str, int]: ...


class InMemoryFeedbackStore:
    def __init__(self) -> None:
        self._events: list[FeedbackEvent] = []

    def append(self, event: FeedbackEvent) -> FeedbackEvent:
        self._events.append(event)
        return event

    def list(
        self,
        *,
        feedback_type: str | None = None,
        limit: int = 100,
    ) -> list[FeedbackEvent]:
        items = self._events
        if feedback_type:
            items = [e for e in items if e.feedback_type == feedback_type]
        return list(reversed(items[-limit:]))

    def count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self._events:
            counts[e.feedback_type] = counts.get(e.feedback_type, 0) + 1
        return counts


class JsonlFeedbackStore:
    """Durable local JSONL store (default offline / fallback backend)."""

    def __init__(self, path: str | Path = "./data/feedback/events.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: FeedbackEvent) -> FeedbackEvent:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return event

    def list(
        self,
        *,
        feedback_type: str | None = None,
        limit: int = 100,
    ) -> list[FeedbackEvent]:
        if not self.path.exists():
            return []
        rows: list[FeedbackEvent] = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                ev = FeedbackEvent.from_dict(json.loads(line))
                if feedback_type and ev.feedback_type != feedback_type:
                    continue
                rows.append(ev)
        return list(reversed(rows[-limit:]))

    def count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.list(limit=10_000):
            counts[e.feedback_type] = counts.get(e.feedback_type, 0) + 1
        return counts


def _resolve_dsn(dsn: str | None) -> str | None:
    if dsn and str(dsn).strip():
        return str(dsn).strip()
    env = os.getenv("POSTGRES_DSN")
    if env and env.strip():
        return env.strip()
    try:
        from agrimind_kernel.config.settings import get_settings

        s = get_settings().postgres_dsn
        return s if s else None
    except Exception:  # noqa: BLE001
        return None


def build_feedback_store(
    *,
    backend: str | None = None,
    path: str = "./data/feedback/events.jsonl",
    dsn: str | None = None,
) -> FeedbackStore:
    """Build a feedback store.

    Backends:
      - ``memory`` — process-local list
      - ``jsonl`` — durable local file
      - ``postgres`` — PostgreSQL (raises if connect/schema fails)
      - ``auto`` — try Postgres when DSN available and ping succeeds, else JSONL

    Env overrides (when *backend* is omitted):
      ``FEEDBACK_STORE`` (default ``auto``), ``POSTGRES_DSN``, ``FEEDBACK_PATH``.
    """
    if backend is None:
        backend = os.getenv("FEEDBACK_STORE") or "auto"
    backend = backend.strip().lower()

    if path == "./data/feedback/events.jsonl":
        path = os.getenv("FEEDBACK_PATH", path)

    if backend == "memory":
        return InMemoryFeedbackStore()

    if backend == "jsonl":
        return JsonlFeedbackStore(path)

    if backend in ("postgres", "postgresql", "pg"):
        resolved = _resolve_dsn(dsn)
        if not resolved:
            raise ValueError(
                "postgres feedback store requires POSTGRES_DSN or settings.postgres_dsn"
            )
        from agrimind_kernel.feedback.postgres_store import PostgresFeedbackStore

        return PostgresFeedbackStore(resolved, ensure_schema_on_init=True)

    if backend == "auto":
        resolved = _resolve_dsn(dsn)
        if resolved:
            from agrimind_kernel.feedback.postgres_store import try_build_postgres_store

            store = try_build_postgres_store(resolved)
            if store is not None:
                logger.info("feedback store: postgres")
                return store
            logger.info(
                "feedback store: postgres unreachable; falling back to jsonl (%s)",
                path,
            )
        else:
            logger.info("feedback store: no DSN; using jsonl (%s)", path)
        return JsonlFeedbackStore(path)

    # Unknown backend → safe local default
    logger.warning("unknown FEEDBACK_STORE=%r; using jsonl", backend)
    return JsonlFeedbackStore(path)


def capture_response_signals(
    store: FeedbackStore,
    *,
    query_id: str | None,
    user_id: str | None,
    query_text: str,
    answer_text: str,
    confidence: float,
    intent: str | None,
    model_version: str | None,
    trace_id: str | None,
    fallback_used: bool,
    requires_review: bool,
    low_confidence_threshold: float = 0.7,
) -> list[FeedbackEvent]:
    """Auto-emit flywheel signals from a chat response (E1)."""
    emitted: list[FeedbackEvent] = []
    if fallback_used or requires_review:
        ev = FeedbackEvent(
            feedback_type=FeedbackType.SAFETY_FALLBACK.value,
            query_id=query_id,
            user_id=user_id,
            query_text=query_text,
            answer_text=answer_text[:2000],
            confidence=confidence,
            intent=intent,
            model_version=model_version,
            trace_id=trace_id,
            reason="fallback_or_review",
        )
        store.append(ev)
        emitted.append(ev)
    if confidence < low_confidence_threshold:
        ev = FeedbackEvent(
            feedback_type=FeedbackType.LOW_CONFIDENCE.value,
            query_id=query_id,
            user_id=user_id,
            query_text=query_text,
            answer_text=answer_text[:2000],
            confidence=confidence,
            intent=intent,
            model_version=model_version,
            trace_id=trace_id,
            reason=f"confidence {confidence:.3f} < {low_confidence_threshold}",
        )
        store.append(ev)
        emitted.append(ev)
    return emitted
