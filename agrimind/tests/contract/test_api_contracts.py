"""Contract tests for API schemas."""
import pytest
from uuid import uuid4
from datetime import datetime
from agrimind_kernel.contracts.query import Query, GeoPoint
from agrimind_kernel.contracts.response import Response, Citation


class TestQueryContract:
    def test_query_with_all_fields(self):
        query = Query(
            query_id=uuid4(),
            text="कपाशीवर बोंडअळी आली आहे, काय करावे?",
            lang="mr",
            modality="text",
            location=GeoPoint(lat=20.5937, lon=78.9629),
            user_id="farmer_123",
        )
        assert query.lang == "mr"
        assert "बोंडअळी" in query.text
    
    def test_query_multilingual(self):
        for lang in ["en", "hi", "mr"]:
            query = Query(
                query_id=uuid4(),
                text="test",
                lang=lang,
                user_id="u1",
            )
            assert query.lang == lang


class TestResponseContract:
    def test_response_with_citations(self):
        citation = Citation(
            source_id="src_1",
            source_type="document",
            url_or_path="s3://bucket/doc.pdf",
            checksum="sha256:abc123",
        )
        response = Response(
            query_id=uuid4(),
            answer="Apply neem oil spray.",
            lang="en",
            citations=[citation],
            confidence=0.92,
            model_version="agrimind-7b-v1.0.0",
            trace_id=str(uuid4()),
        )
        assert response.has_citations is True
        assert len(response.citations) == 1
    
    def test_response_confidence_levels(self):
        response = Response(
            query_id=uuid4(),
            answer="Test",
            lang="en",
            confidence=0.85,
            model_version="v1",
            trace_id="t1",
        )
        assert response.is_high_confidence is True
        assert response.requires_human_review is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
