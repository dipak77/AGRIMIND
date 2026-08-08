"""Postgres-backed flywheel feedback store (psycopg3)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agrimind_kernel.feedback.events import FeedbackEvent

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def normalize_postgres_dsn(dsn: str) -> str:
    """Convert SQLAlchemy-style DSNs to a libpq/psycopg connection string."""
    dsn = (dsn or "").strip()
    if not dsn:
        return dsn
    for prefix in (
        "postgresql+asyncpg://",
        "postgresql+psycopg2://",
        "postgresql+psycopg://",
        "postgres+asyncpg://",
        "postgres+psycopg2://",
        "postgres+psycopg://",
    ):
        if dsn.startswith(prefix):
            rest = dsn[len(prefix) :]
            scheme = "postgresql" if "postgresql" in prefix else "postgres"
            return f"{scheme}://{rest}"
    return dsn


def _parse_created_at(value: Any) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _row_to_event(row: Any) -> FeedbackEvent:
    """Map a DB row (dict-like or sequence) to FeedbackEvent."""
    if hasattr(row, "keys"):
        data = dict(row)
    else:
        # positional order matching SELECT list
        keys = (
            "event_id",
            "feedback_type",
            "query_id",
            "user_id",
            "query_text",
            "answer_text",
            "confidence",
            "intent",
            "model_version",
            "trace_id",
            "reason",
            "metadata",
            "created_at",
            "tenant_id",
        )
        data = dict(zip(keys, row, strict=False))

    meta = data.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}
    if not isinstance(meta, dict):
        meta = dict(meta) if meta else {}

    return FeedbackEvent(
        event_id=str(data.get("event_id") or ""),
        feedback_type=str(data.get("feedback_type") or ""),
        query_id=data.get("query_id"),
        user_id=data.get("user_id"),
        query_text=str(data.get("query_text") or ""),
        answer_text=str(data.get("answer_text") or ""),
        confidence=data.get("confidence"),
        intent=data.get("intent"),
        model_version=data.get("model_version"),
        trace_id=data.get("trace_id"),
        reason=data.get("reason"),
        metadata=meta,
        created_at=_parse_created_at(data.get("created_at")),
        tenant_id=data.get("tenant_id"),
    )


class PostgresFeedbackStore:
    """Durable feedback store backed by PostgreSQL via psycopg3.

    Connection is opened lazily per operation (short-lived) so callers do not
    need to manage pooling for low-volume flywheel traffic. For high volume,
    pass a pre-built connection factory later.
    """

    def __init__(
        self,
        dsn: str,
        *,
        ensure_schema_on_init: bool = True,
        connect_timeout: float = 5.0,
    ) -> None:
        self.dsn = normalize_postgres_dsn(dsn)
        self.connect_timeout = connect_timeout
        self._schema_ready = False
        if ensure_schema_on_init:
            self.ensure_schema()

    def _connect(self):  # type: ignore[no-untyped-def]
        import psycopg
        from psycopg.rows import dict_row

        # libpq connect_timeout is seconds (int); never pass 0 (means wait forever)
        timeout_s = max(1, int(self.connect_timeout) if self.connect_timeout else 5)
        conn = psycopg.connect(
            self.dsn,
            connect_timeout=timeout_s,
            row_factory=dict_row,
            autocommit=False,
        )
        return conn

    def ping(self) -> bool:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return True
        except Exception as exc:  # noqa: BLE001 — ping must never raise
            logger.debug("postgres feedback ping failed: %s", exc)
            return False

    def ensure_schema(self) -> None:
        """Create feedback_events table + indexes if missing."""
        if self._schema_ready:
            return
        sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        self._schema_ready = True
        logger.info("feedback_events schema ensured")

    def append(self, event: FeedbackEvent) -> FeedbackEvent:
        self.ensure_schema()
        meta = event.metadata if isinstance(event.metadata, dict) else {}
        created_at = event.created_at
        # Accept ISO strings; let Postgres parse via timestamptz cast
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO feedback_events (
                        event_id, feedback_type, query_id, user_id,
                        query_text, answer_text, confidence, intent,
                        model_version, trace_id, reason, metadata,
                        created_at, tenant_id
                    ) VALUES (
                        %(event_id)s, %(feedback_type)s, %(query_id)s, %(user_id)s,
                        %(query_text)s, %(answer_text)s, %(confidence)s, %(intent)s,
                        %(model_version)s, %(trace_id)s, %(reason)s, %(metadata)s::jsonb,
                        COALESCE(%(created_at)s::timestamptz, NOW()), %(tenant_id)s
                    )
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    {
                        "event_id": event.event_id,
                        "feedback_type": event.feedback_type,
                        "query_id": event.query_id,
                        "user_id": event.user_id,
                        "query_text": event.query_text or "",
                        "answer_text": event.answer_text or "",
                        "confidence": event.confidence,
                        "intent": event.intent,
                        "model_version": event.model_version,
                        "trace_id": event.trace_id,
                        "reason": event.reason,
                        "metadata": json.dumps(meta, ensure_ascii=False),
                        "created_at": created_at,
                        "tenant_id": getattr(event, "tenant_id", None),
                    },
                )
            conn.commit()
        return event

    def list(
        self,
        *,
        feedback_type: str | None = None,
        limit: int = 100,
    ) -> list[FeedbackEvent]:
        self.ensure_schema()
        limit = max(1, min(int(limit), 10_000))
        if feedback_type:
            query = """
                SELECT event_id, feedback_type, query_id, user_id,
                       query_text, answer_text, confidence, intent,
                       model_version, trace_id, reason, metadata,
                       created_at, tenant_id
                FROM feedback_events
                WHERE feedback_type = %(feedback_type)s
                ORDER BY created_at DESC
                LIMIT %(limit)s
            """
            params: dict[str, Any] = {
                "feedback_type": feedback_type,
                "limit": limit,
            }
        else:
            query = """
                SELECT event_id, feedback_type, query_id, user_id,
                       query_text, answer_text, confidence, intent,
                       model_version, trace_id, reason, metadata,
                       created_at, tenant_id
                FROM feedback_events
                ORDER BY created_at DESC
                LIMIT %(limit)s
            """
            params = {"limit": limit}

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return [_row_to_event(r) for r in rows]

    def count_by_type(self) -> dict[str, int]:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT feedback_type, COUNT(*)::int AS cnt
                    FROM feedback_events
                    GROUP BY feedback_type
                    """
                )
                rows = cur.fetchall()
        out: dict[str, int] = {}
        for r in rows:
            if hasattr(r, "keys"):
                out[str(r["feedback_type"])] = int(r["cnt"])
            else:
                out[str(r[0])] = int(r[1])
        return out

    def close(self) -> None:
        """No persistent connection to close (connect-per-call)."""
        return None


def try_build_postgres_store(
    dsn: str | None,
    *,
    connect_timeout: float = 3.0,
) -> PostgresFeedbackStore | None:
    """Attempt to build and ping a Postgres store; return None on failure.

    Used by ``build_feedback_store(backend="auto")`` for graceful fallback.
    """
    if not dsn or not str(dsn).strip():
        return None
    try:
        import psycopg  # noqa: F401
    except ImportError:
        logger.warning("psycopg not installed; cannot use postgres feedback store")
        return None
    try:
        store = PostgresFeedbackStore(
            dsn,
            ensure_schema_on_init=True,
            connect_timeout=connect_timeout,
        )
        if not store.ping():
            logger.warning("postgres feedback store ping failed; falling back")
            return None
        return store
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "postgres feedback store unavailable (%s); callers should fall back",
            exc,
        )
        return None
