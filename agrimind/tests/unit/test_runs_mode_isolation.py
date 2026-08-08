"""Demo vs real mode isolation + runId folder foundation + cleanup."""

from __future__ import annotations

from pathlib import Path

import pytest

from data_ingestion_service.runs import (
    cleanup_run,
    cleanup_runs,
    create_run,
    is_demo_url,
    list_runs,
    validate_source_for_mode,
)


def test_is_demo_url_blocks_example():
    assert is_demo_url("https://example.com/demo/x") is True
    assert is_demo_url("https://evil.example.net/x") is True
    assert is_demo_url("https://en.wikipedia.org/wiki/Soil_health") is False
    assert is_demo_url("https://icar.org.in/") is False


def test_validate_real_mode_rejects_inline_and_example():
    with pytest.raises(ValueError, match="inline"):
        validate_source_for_mode(
            mode="real",
            source_url="https://en.wikipedia.org/wiki/Agriculture",
            content="mock text",
        )
    with pytest.raises(ValueError, match="demo_or_example"):
        validate_source_for_mode(
            mode="real",
            source_url="https://example.com/demo/cotton",
            content=None,
        )
    # demo allows both
    validate_source_for_mode(
        mode="demo",
        source_url="https://example.com/demo/x",
        content="ok",
    )


def test_run_folder_structure_and_cleanup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    # reload module paths via data_root()
    from data_ingestion_service import runs as runs_mod

    monkeypatch.setattr(runs_mod, "data_root", lambda: tmp_path / "data")

    ctx = create_run("real", label="unit-test")
    assert ctx.run_id.startswith("real-")
    assert ctx.lakehouse_objects.is_dir()
    assert ctx.lakehouse_tables.is_dir()
    assert ctx.jobs_dir.is_dir()
    assert ctx.meta_path().is_file()
    ctx.append_event("stage", {"job_id": "abc", "stage": "download"})
    assert ctx.process_log_path().is_file()
    ctx.save_job_snapshot({"job_id": "abc", "status": "curated", "run_id": ctx.run_id})
    assert (ctx.jobs_dir / "abc.json").is_file()

    listed = list_runs(mode="real", limit=10)
    assert any(r["run_id"] == ctx.run_id for r in listed)

    preview = cleanup_run(ctx.run_id, dry_run=True)
    assert preview["dry_run"] is True
    assert ctx.root.exists()

    deleted = cleanup_run(ctx.run_id, dry_run=False)
    assert deleted["deleted"] is True
    assert not ctx.root.exists()


def test_cleanup_bulk_keep_latest(tmp_path: Path, monkeypatch):
    from data_ingestion_service import runs as runs_mod

    monkeypatch.setattr(runs_mod, "data_root", lambda: tmp_path / "data")
    a = create_run("demo", label="a")
    b = create_run("demo", label="b")
    res = cleanup_runs(mode="demo", keep_latest=1, dry_run=False)
    assert res["runs_touched"] >= 1
    # one demo run should remain
    left = list_runs(mode="demo", limit=20)
    assert len(left) == 1
    assert left[0]["run_id"] in (a.run_id, b.run_id)
