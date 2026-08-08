"""Training eligibility governance gate (P0.6)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, List, Literal


APPROVED_TRAINING_LICENSES = {
    "cc-by-4.0",
    "cc-by-3.0",
    "cc-by-2.0",
    "cc0-1.0",
    "public-domain",
    "mit",
    "apache-2.0",
    "ogdl-india",
}

RESTRICTED_LICENSES = {
    "cc-by-nc-4.0",
    "cc-by-nc-sa-4.0",
    "cc-by-nd-4.0",
    "all-rights-reserved",
    "unknown",
}


@dataclass
class EligibilityRecord:
    document_id: str
    source_url: str
    stage_status: Literal[
        "DISCOVERED",
        "ACCESSIBLE",
        "LICENSE_IDENTIFIED",
        "LICENSE_POLICY_CHECK",
        "TRAINING_ELIGIBLE",
        "APPROVED",
        "QUARANTINED",
    ]
    license_id: str
    license_confidence: float
    training_allowed: bool
    commercial_use_allowed: bool
    attribution_required: bool
    redistribution_allowed: bool
    policy_version: str = "v1.0"
    rejection_reason: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrainingEligibilityGate:
    """Legal & policy gate checking document eligibility for model pretraining."""

    def __init__(self, policy_version: str = "v1.0") -> None:
        self.policy_version = policy_version

    def evaluate_document(
        self,
        document_id: str,
        source_url: str,
        license_id: str,
        license_confidence: float = 1.0,
        is_accessible: bool = True,
    ) -> EligibilityRecord:
        """Evaluate a document through the governance eligibility pipeline."""
        lic_clean = license_id.strip().lower()

        if not is_accessible:
            return EligibilityRecord(
                document_id=document_id,
                source_url=source_url,
                stage_status="QUARANTINED",
                license_id=lic_clean,
                license_confidence=license_confidence,
                training_allowed=False,
                commercial_use_allowed=False,
                attribution_required=True,
                redistribution_allowed=False,
                policy_version=self.policy_version,
                rejection_reason="Document is inaccessible",
            )

        if license_confidence < 0.8:
            return EligibilityRecord(
                document_id=document_id,
                source_url=source_url,
                stage_status="QUARANTINED",
                license_id=lic_clean,
                license_confidence=license_confidence,
                training_allowed=False,
                commercial_use_allowed=False,
                attribution_required=True,
                redistribution_allowed=False,
                policy_version=self.policy_version,
                rejection_reason=f"License confidence too low ({license_confidence:.2f} < 0.80)",
            )

        if lic_clean in RESTRICTED_LICENSES or lic_clean not in APPROVED_TRAINING_LICENSES:
            return EligibilityRecord(
                document_id=document_id,
                source_url=source_url,
                stage_status="QUARANTINED",
                license_id=lic_clean,
                license_confidence=license_confidence,
                training_allowed=False,
                commercial_use_allowed=False,
                attribution_required=True,
                redistribution_allowed=False,
                policy_version=self.policy_version,
                rejection_reason=f"License '{lic_clean}' is not in approved pretraining allow-list",
            )

        # Approved
        return EligibilityRecord(
            document_id=document_id,
            source_url=source_url,
            stage_status="APPROVED",
            license_id=lic_clean,
            license_confidence=license_confidence,
            training_allowed=True,
            commercial_use_allowed=True,
            attribution_required="cc-by" in lic_clean or lic_clean == "ogdl-india",
            redistribution_allowed=True,
            policy_version=self.policy_version,
        )
