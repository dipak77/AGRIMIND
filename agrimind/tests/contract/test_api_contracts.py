"""Contract shape tests (no live HTTP)."""

from agrimind_kernel.contracts import Citation, GeoPoint, Language, Query, Response, SafetyLevel


def test_geopoint_fields():
    g = GeoPoint(latitude=19.07, longitude=72.88)
    assert g.latitude == 19.07


def test_response_review_flag():
    q = Query(text="test", user_id="u")
    r = Response(
        query_id=q.query_id,
        answer="IPM only",
        lang=Language.ENGLISH,
        confidence=0.5,
        model_version="sim",
        trace_id="t",
        safety_level=SafetyLevel.GENERAL,
        safety_flags=["low_confidence"],
        requires_review=True,
    )
    assert r.requires_review is True
    assert r.has_citations is False


def test_citation_checksum():
    c = Citation(
        source_id="s",
        source_type="document",
        url_or_path="s3://x",
        checksum="sha256:1",
        excerpt="e",
    )
    assert c.checksum
