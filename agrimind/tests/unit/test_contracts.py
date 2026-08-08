"""Contract tests for unified kernel."""

from uuid import UUID

from agrimind_kernel.contracts import (
    Citation,
    GeoPoint,
    Language,
    Query,
    QueryModality,
    Response,
    SafetyLevel,
)


def test_query_defaults():
    q = Query(text="Hello cotton", user_id="u1")
    assert isinstance(q.query_id, UUID)
    assert q.lang == Language.ENGLISH
    assert q.modality == QueryModality.TEXT


def test_query_multilingual():
    q = Query(text="कपाशी", lang=Language.MARATHI, user_id="u1")
    assert q.lang == Language.MARATHI


def test_response_requires_confidence():
    r = Response(
        query_id=Query(text="x", user_id="u").query_id,
        answer="Use IPM",
        lang=Language.ENGLISH,
        confidence=0.8,
        model_version="sim",
        trace_id="t",
        safety_level=SafetyLevel.GENERAL,
    )
    assert r.has_citations is False
    assert r.answer == "Use IPM"


def test_citation_provenance():
    c = Citation(
        source_id="s1",
        source_type="document",
        title="ICAR",
        url_or_path="s3://bucket/doc.pdf",
        checksum="sha256:abc",
        excerpt="IPM",
    )
    assert c.checksum.startswith("sha256")


def test_geopoint():
    g = GeoPoint(latitude=19.07, longitude=72.87, district="Pune")
    assert g.district == "Pune"
