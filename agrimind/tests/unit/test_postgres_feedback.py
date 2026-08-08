"""Unit tests for Postgres feedback store (mocked — no live DB required)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agrimind_kernel.feedback.events import (
    FeedbackEvent,
    FeedbackType,
    JsonlFeedbackStore,
    InMemoryFeedbackStore,
    build_feedback_store,
)
from agrimind_kernel.feedback.postgres_store import (
    PostgresFeedbackStore,
    normalize_postgres_dsn,
    try_build_postgres_store,
    _row_to_event,
)


# ---------------------------------------------------------------------------
# DSN helpers
# ---------------------------------------------------------------------------


def test_normalize_postgres_dsn_strips_asyncpg_driver():
    assert (
        normalize_postgres_dsn(
            "postgresql+asyncpg://agrimind:secret@localhost:5432/agrimind"
        )
        == "postgresql://agrimind:secret@localhost:5432/agrimind"
    )


def test_normalize_postgres_dsn_passthrough():
    dsn = "postgresql://u:p@db:5432/db"
    assert normalize_postgres_dsn(dsn) == dsn


def test_normalize_psycopg_driver_prefix():
    assert (
        normalize_postgres_dsn("postgresql+psycopg://u:p@h/db")
        == "postgresql://u:p@h/db"
    )


# ---------------------------------------------------------------------------
# Row mapping
# ---------------------------------------------------------------------------


def test_row_to_event_from_dict():
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    ev = _row_to_event(
        {
            "event_id": "e1",
            "feedback_type": "thumbs_down",
            "query_id": "q1",
            "user_id": "u1",
            "query_text": "pest?",
            "answer_text": "IPM",
            "confidence": 0.4,
            "intent": "pest",
            "model_version": "m1",
            "trace_id": "t1",
            "reason": "bad",
            "metadata": {"k": "v"},
            "created_at": now,
            "tenant_id": "tenant-a",
        }
    )
    assert ev.event_id == "e1"
    assert ev.feedback_type == FeedbackType.THUMBS_DOWN.value
    assert ev.confidence == 0.4
    assert ev.metadata == {"k": "v"}
    assert ev.tenant_id == "tenant-a"
    assert "2026-01-02" in ev.created_at


def test_row_to_event_metadata_json_string():
    ev = _row_to_event(
        {
            "event_id": "e2",
            "feedback_type": "low_confidence",
            "query_id": None,
            "user_id": None,
            "query_text": "",
            "answer_text": "",
            "confidence": None,
            "intent": None,
            "model_version": None,
            "trace_id": None,
            "reason": None,
            "metadata": '{"source": "test"}',
            "created_at": "2026-01-01T00:00:00+00:00",
            "tenant_id": None,
        }
    )
    assert ev.metadata == {"source": "test"}


# ---------------------------------------------------------------------------
# PostgresFeedbackStore with mocked connection
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, fetchall_rows: list[Any] | None = None) -> None:
        self.executed: list[tuple[str, Any]] = []
        self._fetchall_rows = fetchall_rows or []
        self._fetchone_row: Any = {"?column?": 1}

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> Any:
        return self._fetchone_row

    def fetchall(self) -> list[Any]:
        return list(self._fetchall_rows)

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _FakeConn:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.committed = False

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> "_FakeConn":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _patched_store(
    fetchall_rows: list[Any] | None = None,
) -> tuple[PostgresFeedbackStore, _FakeCursor, _FakeConn]:
    cur = _FakeCursor(fetchall_rows=fetchall_rows)
    conn = _FakeConn(cur)
    store = PostgresFeedbackStore.__new__(PostgresFeedbackStore)
    store.dsn = "postgresql://test:test@localhost:5432/test"
    store.connect_timeout = 1.0
    store._schema_ready = True  # skip real schema apply

    @contextmanager
    def _connect():
        yield conn

    store._connect = _connect  # type: ignore[method-assign]
    return store, cur, conn


def test_postgres_append_executes_insert():
    store, cur, conn = _patched_store()
    ev = FeedbackEvent(
        event_id="evt-1",
        feedback_type=FeedbackType.THUMBS_UP.value,
        query_text="hello",
        answer_text="world",
        confidence=0.9,
        tenant_id="t1",
        metadata={"a": 1},
    )
    out = store.append(ev)
    assert out is ev
    assert conn.committed is True
    assert len(cur.executed) == 1
    sql, params = cur.executed[0]
    assert "INSERT INTO feedback_events" in sql
    assert params["event_id"] == "evt-1"
    assert params["tenant_id"] == "t1"
    assert '"a": 1' in params["metadata"] or params["metadata"] == '{"a": 1}'


def test_postgres_list_maps_rows():
    rows = [
        {
            "event_id": "e9",
            "feedback_type": "thumbs_down",
            "query_id": None,
            "user_id": None,
            "query_text": "q",
            "answer_text": "a",
            "confidence": 0.2,
            "intent": None,
            "model_version": None,
            "trace_id": None,
            "reason": None,
            "metadata": {},
            "created_at": datetime.now(timezone.utc),
            "tenant_id": None,
        }
    ]
    store, cur, _conn = _patched_store(fetchall_rows=rows)
    result = store.list(limit=10)
    assert len(result) == 1
    assert result[0].event_id == "e9"
    assert "FROM feedback_events" in cur.executed[0][0]


def test_postgres_list_with_type_filter():
    store, cur, _conn = _patched_store(fetchall_rows=[])
    store.list(feedback_type="low_confidence", limit=5)
    sql, params = cur.executed[0]
    assert "feedback_type" in sql
    assert params["feedback_type"] == "low_confidence"
    assert params["limit"] == 5


def test_postgres_count_by_type():
    store, _cur, _conn = _patched_store(
        fetchall_rows=[
            {"feedback_type": "thumbs_up", "cnt": 3},
            {"feedback_type": "thumbs_down", "cnt": 1},
        ]
    )
    counts = store.count_by_type()
    assert counts == {"thumbs_up": 3, "thumbs_down": 1}


def test_postgres_ensure_schema_runs_sql_file():
    cur = _FakeCursor()
    conn = _FakeConn(cur)
    store = PostgresFeedbackStore.__new__(PostgresFeedbackStore)
    store.dsn = "postgresql://x"
    store.connect_timeout = 1.0
    store._schema_ready = False

    @contextmanager
    def _connect():
        yield conn

    store._connect = _connect  # type: ignore[method-assign]
    store.ensure_schema()
    assert store._schema_ready is True
    assert conn.committed is True
    assert any("feedback_events" in (sql or "") for sql, _ in cur.executed)
    # second call is no-op
    n = len(cur.executed)
    store.ensure_schema()
    assert len(cur.executed) == n


# ---------------------------------------------------------------------------
# try_build / build_feedback_store auto fallback
# ---------------------------------------------------------------------------


def test_try_build_postgres_store_returns_none_on_connect_error():
    """Offline-safe: mock connect failure — no live network."""
    with patch(
        "agrimind_kernel.feedback.postgres_store.PostgresFeedbackStore",
        side_effect=OSError("connection refused"),
    ):
        result = try_build_postgres_store(
            "postgresql://nobody:bad@127.0.0.1:1/none",
            connect_timeout=1.0,
        )
    assert result is None


def test_try_build_postgres_store_returns_none_when_ping_fails():
    mock_store = MagicMock(spec=PostgresFeedbackStore)
    mock_store.ping.return_value = False
    with patch(
        "agrimind_kernel.feedback.postgres_store.PostgresFeedbackStore",
        return_value=mock_store,
    ):
        result = try_build_postgres_store("postgresql://u:p@localhost/db")
    assert result is None


def test_try_build_postgres_store_empty_dsn():
    assert try_build_postgres_store(None) is None
    assert try_build_postgres_store("") is None
    assert try_build_postgres_store("   ") is None


def test_build_feedback_store_memory():
    store = build_feedback_store(backend="memory")
    assert isinstance(store, InMemoryFeedbackStore)


def test_build_feedback_store_jsonl(tmp_path):
    path = tmp_path / "fb.jsonl"
    store = build_feedback_store(backend="jsonl", path=str(path))
    assert isinstance(store, JsonlFeedbackStore)
    store.append(FeedbackEvent(feedback_type="thumbs_up", query_text="x"))
    assert path.exists()


def test_build_feedback_store_auto_falls_back_when_dsn_unreachable(tmp_path):
    path = tmp_path / "fallback.jsonl"
    with patch(
        "agrimind_kernel.feedback.postgres_store.try_build_postgres_store",
        return_value=None,
    ):
        store = build_feedback_store(
            backend="auto",
            path=str(path),
            dsn="postgresql://nobody:bad@127.0.0.1:1/none",
        )
    assert isinstance(store, JsonlFeedbackStore)
    assert store.path == path


def test_build_feedback_store_auto_no_dsn_uses_jsonl(tmp_path, monkeypatch):
    path = tmp_path / "nodsn.jsonl"
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    with patch(
        "agrimind_kernel.feedback.events._resolve_dsn",
        return_value=None,
    ):
        store = build_feedback_store(backend="auto", path=str(path), dsn=None)
    assert isinstance(store, JsonlFeedbackStore)


def test_build_feedback_store_auto_uses_postgres_when_try_succeeds(tmp_path):
    mock_store = MagicMock(spec=PostgresFeedbackStore)
    with patch(
        "agrimind_kernel.feedback.postgres_store.try_build_postgres_store",
        return_value=mock_store,
    ):
        store = build_feedback_store(
            backend="auto",
            path=str(tmp_path / "x.jsonl"),
            dsn="postgresql://u:p@localhost/db",
        )
    assert store is mock_store


def test_build_feedback_store_postgres_requires_dsn(monkeypatch):
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    with patch(
        "agrimind_kernel.feedback.events._resolve_dsn",
        return_value=None,
    ):
        with pytest.raises(ValueError, match="POSTGRES_DSN"):
            build_feedback_store(backend="postgres", dsn=None)


def test_build_feedback_store_postgres_wires_store():
    instance = MagicMock(spec=PostgresFeedbackStore)
    with patch(
        "agrimind_kernel.feedback.postgres_store.PostgresFeedbackStore",
        return_value=instance,
    ) as mock_pg:
        store = build_feedback_store(
            backend="postgres",
            dsn="postgresql://u:p@localhost/db",
        )
        mock_pg.assert_called_once()
        assert store is instance


def test_feedback_event_tenant_id_roundtrip():
    ev = FeedbackEvent(
        feedback_type=FeedbackType.EXPERT_CORRECTION.value,
        query_text="q",
        tenant_id="ten-1",
    )
    d = ev.to_dict()
    assert d["tenant_id"] == "ten-1"
    restored = FeedbackEvent.from_dict(d)
    assert restored.tenant_id == "ten-1"
