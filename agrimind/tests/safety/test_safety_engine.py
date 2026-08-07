"""Safety tests for the safety engine."""
import pytest
from agrimind_kernel.contracts.safety import SafetyLevel, SafetyPolicy, SafetyCheckResult


class TestSafetyPolicy:
    def test_default_policy_blocks_unsafe_dosage(self):
        policy = SafetyPolicy()
        result = policy.check_content(
            "Mix 500ml of pesticide per liter of water",
            confidence=0.60
        )
        assert result.is_safe is False
        assert result.blocked_reason is not None
    
    def test_high_confidence_allows_chemical_advice(self):
        policy = SafetyPolicy()
        result = policy.check_content(
            "Use neem oil as per label instructions",
            confidence=0.96
        )
        assert result.is_safe is True
    
    def test_banned_chemical_blocked(self):
        policy = SafetyPolicy()
        result = policy.check_content(
            "Use DDT for pest control",
            confidence=0.99
        )
        assert result.is_safe is False


class TestSafetyLevels:
    def test_chemical_dosage_requires_high_confidence(self):
        assert SafetyLevel.CHEMICAL_DOSAGE.min_confidence == 0.95
    
    def test_general_advisory_lower_threshold(self):
        assert SafetyLevel.GENERAL_ADVISORY.min_confidence == 0.70


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
