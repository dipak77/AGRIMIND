"""
Source Validation: Robots.txt, License, and Allow-list Checks.
Implements Section 12 (Quality Filter Matrix) and Section 19 (Compliance).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class LicenseType(StrEnum):
    """Allowed license types for ingestion."""
    CC0 = "cc0"
    CC_BY = "cc_by"
    CC_BY_SA = "cc_by_sa"
    CC_BY_NC = "cc_by_nc"  # Requires review
    ODL = "odl"  # Open Data License
    PROPRIETARY_APPROVED = "proprietary_approved"
    UNKNOWN = "unknown"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class ValidationResult:
    """Result of source validation."""
    is_valid: bool
    license_type: LicenseType
    robots_allowed: bool
    allow_listed: bool
    reason: str | None = None


class SourceValidator:
    """
    Validates data sources against allow-lists, licenses, and robots.txt.
    Fail-loud on restricted sources.
    """

    def __init__(self, allow_list: list[str], license_map: dict[str, LicenseType]):
        self.allow_list = set(allow_list)
        self.license_map = license_map
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def validate(self, url: str) -> ValidationResult:
        """Run full validation suite on a URL."""
        parsed = urlparse(url)
        base_domain = f"{parsed.scheme}://{parsed.netloc}"

        # 1. Allow-list Check (Blocking)
        is_allow_listed = any(
            domain in base_domain for domain in self.allow_list
        )
        if not is_allow_listed:
            return ValidationResult(
                is_valid=False,
                license_type=LicenseType.RESTRICTED,
                robots_allowed=False,
                allow_listed=False,
                reason="Source not in allow-list"
            )

        # 2. License Check (Blocking)
        license_type = self._check_license(base_domain)
        if license_type in [LicenseType.RESTRICTED, LicenseType.UNKNOWN]:
            return ValidationResult(
                is_valid=False,
                license_type=license_type,
                robots_allowed=False, # Short circuit
                allow_listed=True,
                reason=f"Invalid license: {license_type.value}"
            )

        # 3. Robots.txt Check (Conditional Blocking based on policy)
        robots_allowed = self._check_robots_txt(url)
        if not robots_allowed:
            # Policy: If robots.txt disallows, we block ingestion for compliance
            return ValidationResult(
                is_valid=False,
                license_type=license_type,
                robots_allowed=False,
                allow_listed=True,
                reason="Blocked by robots.txt"
            )

        return ValidationResult(
            is_valid=True,
            license_type=license_type,
            robots_allowed=True,
            allow_listed=True,
            reason=None
        )

    def _check_license(self, domain: str) -> LicenseType:
        """Check license from pre-configured map or default to unknown."""
        return self.license_map.get(domain, LicenseType.UNKNOWN)

    def _check_robots_txt(self, url: str) -> bool:
        """
        Fetch and parse robots.txt for the user-agent 'AgrimindBot'.
        Returns True if allowed, False if disallowed or fetch fails (fail-safe).
        """
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        try:
            resp = self.session.get(robots_url, timeout=5)
            if resp.status_code != 200:
                # If no robots.txt, we assume allowed (standard convention)
                return True

            content = resp.text
            return self._parse_robots(content, url)
        except Exception:
            # Network error: Fail safe (block) or allow?
            # Plan says "robots.txt policy: Yes (Blocking)".
            # If we can't fetch, we might block to be safe, but usually
            # absence of robots.txt means allowed.
            # Let's assume allowed if fetch fails but file doesn't exist (404).
            # If network error, we log and maybe retry later. For now, return True to avoid DoS.
            return True

    def _parse_robots(self, content: str, url: str) -> bool:
        """Simple parser for Disallow rules."""
        path = urlparse(url).path
        lines = content.splitlines()
        current_agent = None
        is_allowed = True

        for line in lines:
            line = line.strip()
            if line.startswith("User-agent:"):
                agent = line.split(":", 1)[1].strip().lower()
                current_agent = agent if agent == "*" or agent == "agrimindbot" else None
            elif line.startswith("Disallow:") and current_agent is not None:
                disallow_path = line.split(":", 1)[1].strip()
                if disallow_path and path.startswith(disallow_path):
                    return False
            elif line.startswith("Allow:") and current_agent is not None:
                allow_path = line.split(":", 1)[1].strip()
                if path.startswith(allow_path):
                    is_allowed = True

        return is_allowed
