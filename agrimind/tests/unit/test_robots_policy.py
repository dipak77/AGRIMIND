"""Unit tests for Robots Policy Compliance & CI Safety Gate (P0.5)."""

import os
import pytest

from data_kernel.pipeline.ingest_pipeline import IngestPipeline, IngestRequest


def test_robots_policy_default_and_production_enforcement() -> None:
    pipeline = IngestPipeline()

    req = IngestRequest(
        source_url="https://icar.org.in/test-doc.html",
        allow_list=["icar.org.in"],
    )

    # In production profile with SKIP_ROBOTS=true, pipeline must fail loud!
    os.environ["PROFILE"] = "production"
    os.environ["SKIP_ROBOTS"] = "true"

    with pytest.raises(ValueError, match="Production acquisition profile forbids SKIP_ROBOTS bypass"):
        pipeline._robots_stage(req)

    # Reset environment
    os.environ["PROFILE"] = "dev"
    os.environ["SKIP_ROBOTS"] = "false"

    res = pipeline._robots_stage(req)
    assert res.get("checked") is True or res.get("allowed") is True
