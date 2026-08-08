"""Tests for source validation: allow-list, license, and robots.txt."""
import pytest

from data_kernel.pipeline.validators import (
    LicenseType,
    SourceValidator,
)


class TestLicenseType:
    """Test LicenseType enum values."""

    def test_license_type_values(self):
        """Verify all expected license types exist."""
        assert LicenseType.CC0.value == "cc0"
        assert LicenseType.CC_BY.value == "cc_by"
        assert LicenseType.RESTRICTED.value == "restricted"
        assert LicenseType.UNKNOWN.value == "unknown"


class TestSourceValidator:
    """Test SourceValidator functionality."""

    @pytest.fixture
    def validator(self):
        """Create a validator with test configuration."""
        allow_list = ["icar.org.in", "agri.gov.in", "wikipedia.org"]
        license_map = {
            "https://icar.org.in": LicenseType.CC_BY,
            "https://agri.gov.in": LicenseType.CC0,
            "https://wikipedia.org": LicenseType.CC_BY_SA,
            "https://restricted.com": LicenseType.RESTRICTED,
        }
        return SourceValidator(allow_list=allow_list, license_map=license_map)

    def test_allow_listed_source_valid(self, validator, monkeypatch):
        """Test that allow-listed sources with valid licenses pass."""
        # Mock robots.txt to return allowed
        monkeypatch.setattr(validator, "_check_robots_txt", lambda url: True)

        result = validator.validate("https://icar.org.in/crop-guide.pdf")

        assert result.is_valid is True
        assert result.license_type == LicenseType.CC_BY
        assert result.robots_allowed is True
        assert result.allow_listed is True
        assert result.reason is None

    def test_non_allow_listed_source_blocked(self, validator):
        """Test that non-allow-listed sources are blocked."""
        result = validator.validate("https://evil-site.com/malware.pdf")

        assert result.is_valid is False
        assert result.license_type == LicenseType.RESTRICTED
        assert result.allow_listed is False
        assert "not in allow-list" in result.reason

    def test_unknown_license_blocked(self, validator, monkeypatch):
        """Test that sources with unknown licenses are blocked."""
        monkeypatch.setattr(validator, "_check_robots_txt", lambda url: True)

        # Domain not in license_map -> UNKNOWN
        result = validator.validate("https://unknown-domain.com/data.pdf")

        # Should fail at allow-list first
        assert result.is_valid is False
        assert result.allow_listed is False

    def test_restricted_license_blocked(self, validator, monkeypatch):
        """Test that restricted licenses are blocked."""
        monkeypatch.setattr(validator, "_check_robots_txt", lambda url: True)

        # Add to allow_list temporarily for this test
        validator.allow_list.add("restricted.com")
        result = validator.validate("https://restricted.com/data.pdf")

        assert result.is_valid is False
        assert result.license_type == LicenseType.RESTRICTED
        assert "Invalid license" in result.reason

    def test_robots_txt_blocked(self, validator, monkeypatch):
        """Test that sources blocked by robots.txt fail validation."""
        monkeypatch.setattr(validator, "_check_robots_txt", lambda url: False)

        result = validator.validate("https://icar.org.in/secret-data.pdf")

        assert result.is_valid is False
        assert result.robots_allowed is False
        assert "Blocked by robots.txt" in result.reason

    def test_cc_by_nc_requires_review(self, validator, monkeypatch):
        """Test that CC BY-NC license is flagged (not automatically blocked but needs review)."""
        # Add NC license to map
        validator.license_map["https://nc-site.org"] = LicenseType.CC_BY_NC
        validator.allow_list.add("nc-site.org")
        monkeypatch.setattr(validator, "_check_robots_txt", lambda url: True)

        result = validator.validate("https://nc-site.org/data.pdf")

        # Currently CC_BY_NC is not blocked, but could be flagged for review
        assert result.is_valid is True
        assert result.license_type == LicenseType.CC_BY_NC


class TestRobotsParser:
    """Test robots.txt parsing logic."""

    @pytest.fixture
    def validator(self):
        """Create minimal validator for robots testing."""
        return SourceValidator(
            allow_list=["test.com"],
            license_map={"https://test.com": LicenseType.CC0}
        )

    def test_parse_robots_disallow_all(self, validator):
        """Test parsing robots.txt that disallows all paths."""
        content = """
User-agent: *
Disallow: /
"""
        result = validator._parse_robots(content, "https://test.com/secret")
        assert result is False

    def test_parse_robots_allow_all(self, validator):
        """Test parsing robots.txt that allows all paths."""
        content = """
User-agent: *
Disallow:
"""
        result = validator._parse_robots(content, "https://test.com/public")
        assert result is True

    def test_parse_robots_specific_path(self, validator):
        """Test parsing robots.txt with specific path restrictions."""
        content = """
User-agent: *
Disallow: /admin
Allow: /public
"""
        # Admin path should be blocked
        assert validator._parse_robots(content, "https://test.com/admin/users") is False
        # Public path should be allowed
        assert validator._parse_robots(content, "https://test.com/public/data") is True

    def test_parse_robots_agrimindbot_agent(self, validator):
        """Test parsing robots.txt with specific AgrimindBot agent."""
        content = """
User-agent: AgrimindBot
Disallow: /private
Allow: /open
"""
        # Private path blocked for AgrimindBot
        assert validator._parse_robots(content, "https://test.com/private") is False
        # Open path allowed
        assert validator._parse_robots(content, "https://test.com/open") is True
