"""Unit tests for Training Eligibility Governance Gate (P0.6)."""

from data_kernel.governance.training_eligibility import TrainingEligibilityGate


def test_approved_license_evaluation() -> None:
    gate = TrainingEligibilityGate()
    rec = gate.evaluate_document(
        document_id="doc-001",
        source_url="https://icar.org.in/bulletin.pdf",
        license_id="CC-BY-4.0",
        license_confidence=0.98,
    )
    assert rec.stage_status == "APPROVED"
    assert rec.training_allowed is True
    assert rec.attribution_required is True
    assert rec.rejection_reason is None


def test_unidentified_license_quarantined() -> None:
    gate = TrainingEligibilityGate()
    rec = gate.evaluate_document(
        document_id="doc-002",
        source_url="https://unknown-site.org/data.pdf",
        license_id="unknown",
        license_confidence=0.50,
    )
    assert rec.stage_status == "QUARANTINED"
    assert rec.training_allowed is False
    assert "License confidence too low" in (rec.rejection_reason or "")


def test_restricted_license_quarantined() -> None:
    gate = TrainingEligibilityGate()
    rec = gate.evaluate_document(
        document_id="doc-003",
        source_url="https://commercial.com/article.pdf",
        license_id="all-rights-reserved",
        license_confidence=0.99,
    )
    assert rec.stage_status == "QUARANTINED"
    assert rec.training_allowed is False
    assert "not in approved pretraining allow-list" in (rec.rejection_reason or "")
