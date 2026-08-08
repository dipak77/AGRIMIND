"""License allow-list filter for curation."""

from __future__ import annotations

from dataclasses import dataclass

ALLOWED = {
    "cc0",
    "cc-by",
    "cc_by",
    "cc-by-sa",
    "cc_by_sa",
    "odl",
    "government_open",
    "government-open",
    "godl-india",
    "godl_india",
    "public-domain",
    "public_domain",
    "cc-by-3.0-igo",
    "cc_by_3.0_igo",
    "cc-by-4.0",
    "cc_by_4.0",
    "cc-by-sa-4.0",
    "cc_by_sa_4.0",
    "cc0-us-gov-pd",
    "proprietary_approved",
    "unknown",  # local/dev may pass with review flag
}


@dataclass
class LicenseResult:
    allowed: bool
    license: str
    requires_review: bool
    reason: str | None = None


class LicenseFilter:
    def check(self, license_str: str) -> LicenseResult:
        raw = (license_str or "unknown").strip().lower()
        lic = raw.replace(" ", "_")
        # normalize common open-knowledge tags from discovery
        try:
            from data_kernel.sources.discovery import normalize_license

            lic = normalize_license(raw)
        except Exception:
            pass
        if lic in ("restricted", "all_rights_reserved", "closed"):
            return LicenseResult(
                allowed=False,
                license=lic,
                requires_review=True,
                reason="restricted_license",
            )
        # accept both hyphen and underscore forms
        if lic in ALLOWED or lic.replace("-", "_") in ALLOWED or lic.replace("_", "-") in ALLOWED:
            return LicenseResult(
                allowed=True,
                license=lic,
                requires_review=lic in ("unknown", "proprietary_approved", "cc_by_nc", "cc-by-nc"),
            )
        # unknown exotic license → quarantine for review
        return LicenseResult(
            allowed=False,
            license=lic,
            requires_review=True,
            reason="license_not_in_allow_list",
        )
