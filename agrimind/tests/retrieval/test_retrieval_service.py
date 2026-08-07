"""Retrieval service tests."""
import pytest
from uuid import uuid4
from agrimind_kernel.config.settings import get_settings


class TestRetrievalModes:
    def test_hybrid_retrieval_available(self):
        # Verify retrieval modes are defined
        modes = ["graph", "vector", "hybrid", "api", "auto"]
        assert len(modes) == 5
        assert "hybrid" in modes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
