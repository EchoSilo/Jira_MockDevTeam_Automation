"""Tests for pre-execution validators with optimistic locking.

These tests validate:
- Status validation (match/mismatch)
- Sprint membership validation
- Assignee validation
- Optimistic locking via Jira's updated timestamp
- API error handling (404, timeout)

Requirements covered:
- RECON-01: Pre-execution validation checks Jira ticket state
- RECON-07: Optimistic locking via updated timestamp
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import pendulum

from src.reconciliation.models import ValidationResult
from src.reconciliation.validators import (
    PreExecutionValidator,
    OptimisticLockingValidator,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_jira_client():
    """Create a mock JiraClient for testing."""
    return Mock()


@pytest.fixture
def pre_validator(mock_jira_client):
    """Create a PreExecutionValidator with mock JiraClient."""
    return PreExecutionValidator(jira_client=mock_jira_client)


@pytest.fixture
def optimistic_validator(mock_jira_client):
    """Create an OptimisticLockingValidator with mock JiraClient."""
    return OptimisticLockingValidator(jira_client=mock_jira_client)


def create_mock_issue(
    status: str = "In Progress",
    assignee_id: str = None,
    assignee_name: str = None,
    updated: str = "2026-01-28T10:00:00.000+0000",
):
    """Create a mock Jira issue with configurable fields."""
    issue = Mock()
    issue.fields = Mock()
    issue.fields.status = Mock()
    issue.fields.status.name = status
    issue.fields.updated = updated

    if assignee_id:
        issue.fields.assignee = Mock()
        issue.fields.assignee.accountId = assignee_id
        issue.fields.assignee.displayName = assignee_name or "Test User"
    else:
        issue.fields.assignee = None

    return issue


# =============================================================================
# ValidationResult Model Tests
# =============================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """ValidationResult with valid=True should have no reason."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.reason is None
        assert result.actual_state is None
        assert result.expected_state is None

    def test_invalid_result_with_reason(self):
        """ValidationResult with valid=False should have descriptive reason."""
        result = ValidationResult(
            valid=False,
            reason="Status changed: expected 'In Progress', got 'Done'",
            actual_state={"status": "Done"},
            expected_state={"status": "In Progress"},
        )
        assert result.valid is False
        assert "Status changed" in result.reason
        assert result.actual_state["status"] == "Done"
        assert result.expected_state["status"] == "In Progress"


# =============================================================================
# PreExecutionValidator.validate_status Tests
# =============================================================================


class TestPreExecutionValidatorStatus:
    """Tests for validate_status method."""

    def test_status_matches_returns_valid(self, pre_validator, mock_jira_client):
        """When ticket status matches expected, validation should pass."""
        mock_jira_client.get_issue.return_value = create_mock_issue(
            status="In Progress"
        )

        result = pre_validator.validate_status("ESCRUM-123", "In Progress")

        assert result.valid is True
        assert result.reason is None
        mock_jira_client.get_issue.assert_called_once_with("ESCRUM-123")

    def test_status_mismatch_returns_invalid(self, pre_validator, mock_jira_client):
        """When ticket status differs from expected, validation should fail."""
        mock_jira_client.get_issue.return_value = create_mock_issue(status="Done")

        result = pre_validator.validate_status("ESCRUM-123", "In Progress")

        assert result.valid is False
        assert "Status changed" in result.reason
        assert "expected 'In Progress'" in result.reason
        assert "got 'Done'" in result.reason
        assert result.actual_state["status"] == "Done"
        assert result.expected_state["status"] == "In Progress"

    def test_status_case_sensitive_comparison(self, pre_validator, mock_jira_client):
        """Status comparison should be case-sensitive (Jira uses exact names)."""
        mock_jira_client.get_issue.return_value = create_mock_issue(
            status="in progress"  # Lowercase
        )

        result = pre_validator.validate_status("ESCRUM-123", "In Progress")

        # Case mismatch should be treated as invalid
        assert result.valid is False

    def test_various_status_mismatches(self, pre_validator, mock_jira_client):
        """Test various status mismatch scenarios."""
        test_cases = [
            ("To Do", "In Progress"),
            ("In Progress", "Ready for QA"),
            ("Ready for QA", "Done"),
            ("Done", "To Do"),
        ]

        for expected, actual in test_cases:
            mock_jira_client.get_issue.return_value = create_mock_issue(status=actual)
            result = pre_validator.validate_status("ESCRUM-123", expected)
            assert result.valid is False, f"Expected {expected}, got {actual}"
            assert result.actual_state["status"] == actual


# =============================================================================
# PreExecutionValidator.validate_sprint_membership Tests
# =============================================================================


class TestPreExecutionValidatorSprintMembership:
    """Tests for validate_sprint_membership method."""

    def test_expected_in_sprint_and_is_in_sprint(
        self, pre_validator, mock_jira_client
    ):
        """When ticket expected in sprint and is in sprint, validation passes."""
        mock_jira_client.is_issue_in_active_sprint.return_value = True

        result = pre_validator.validate_sprint_membership(
            "ESCRUM-123", expected_in_sprint=True
        )

        assert result.valid is True
        mock_jira_client.is_issue_in_active_sprint.assert_called_once_with("ESCRUM-123")

    def test_expected_in_sprint_but_not_in_sprint(
        self, pre_validator, mock_jira_client
    ):
        """When ticket expected in sprint but removed, validation fails."""
        mock_jira_client.is_issue_in_active_sprint.return_value = False

        result = pre_validator.validate_sprint_membership(
            "ESCRUM-123", expected_in_sprint=True
        )

        assert result.valid is False
        assert "Sprint membership changed" in result.reason
        assert result.actual_state["in_active_sprint"] is False
        assert result.expected_state["in_active_sprint"] is True

    def test_expected_not_in_sprint_and_not_in_sprint(
        self, pre_validator, mock_jira_client
    ):
        """When ticket expected not in sprint and isn't, validation passes."""
        mock_jira_client.is_issue_in_active_sprint.return_value = False

        result = pre_validator.validate_sprint_membership(
            "ESCRUM-123", expected_in_sprint=False
        )

        assert result.valid is True

    def test_expected_not_in_sprint_but_is_in_sprint(
        self, pre_validator, mock_jira_client
    ):
        """When ticket expected not in sprint but is added, validation fails."""
        mock_jira_client.is_issue_in_active_sprint.return_value = True

        result = pre_validator.validate_sprint_membership(
            "ESCRUM-123", expected_in_sprint=False
        )

        assert result.valid is False
        assert "Sprint membership changed" in result.reason


# =============================================================================
# PreExecutionValidator.validate_assignee Tests
# =============================================================================


class TestPreExecutionValidatorAssignee:
    """Tests for validate_assignee method."""

    def test_assignee_matches_expected(self, pre_validator, mock_jira_client):
        """When assignee matches expected, validation passes."""
        mock_jira_client.get_issue.return_value = create_mock_issue(
            assignee_id="user-123"
        )

        result = pre_validator.validate_assignee("ESCRUM-123", expected_assignee_id="user-123")

        assert result.valid is True

    def test_assignee_differs_from_expected(self, pre_validator, mock_jira_client):
        """When assignee differs from expected, validation fails."""
        mock_jira_client.get_issue.return_value = create_mock_issue(
            assignee_id="user-456"
        )

        result = pre_validator.validate_assignee("ESCRUM-123", expected_assignee_id="user-123")

        assert result.valid is False
        assert "Assignee changed" in result.reason
        assert result.actual_state["assignee_id"] == "user-456"
        assert result.expected_state["assignee_id"] == "user-123"

    def test_expected_unassigned_and_is_unassigned(self, pre_validator, mock_jira_client):
        """When expecting unassigned and ticket is unassigned, validation passes."""
        mock_jira_client.get_issue.return_value = create_mock_issue(assignee_id=None)

        result = pre_validator.validate_assignee("ESCRUM-123", expected_assignee_id=None)

        assert result.valid is True

    def test_expected_unassigned_but_is_assigned(self, pre_validator, mock_jira_client):
        """When expecting unassigned but ticket is assigned, validation fails."""
        mock_jira_client.get_issue.return_value = create_mock_issue(
            assignee_id="user-123"
        )

        result = pre_validator.validate_assignee("ESCRUM-123", expected_assignee_id=None)

        assert result.valid is False
        assert "Assignee changed" in result.reason


# =============================================================================
# OptimisticLockingValidator Tests
# =============================================================================


class TestOptimisticLockingValidator:
    """Tests for optimistic locking via Jira's updated timestamp."""

    def test_ticket_not_modified_returns_valid(
        self, optimistic_validator, mock_jira_client
    ):
        """When ticket not modified after last_known, validation passes."""
        # Ticket updated at 10:00, last known is 10:00
        mock_jira_client.get_issue.return_value = create_mock_issue(
            status="In Progress",
            updated="2026-01-28T10:00:00.000+0000",
        )

        result = optimistic_validator.validate_with_timestamp(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            last_known_updated="2026-01-28T10:00:00+00:00",
        )

        assert result.valid is True

    def test_ticket_modified_after_last_known_returns_invalid(
        self, optimistic_validator, mock_jira_client
    ):
        """When ticket modified after last_known, validation fails."""
        # Ticket updated at 10:30, last known is 10:00
        mock_jira_client.get_issue.return_value = create_mock_issue(
            status="In Progress",
            updated="2026-01-28T10:30:00.000+0000",
        )

        result = optimistic_validator.validate_with_timestamp(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            last_known_updated="2026-01-28T10:00:00+00:00",
        )

        assert result.valid is False
        assert "Optimistic lock failed" in result.reason
        assert "modified" in result.reason.lower()

    def test_status_mismatch_with_optimistic_locking(
        self, optimistic_validator, mock_jira_client
    ):
        """When status changes (even with same timestamp), validation fails."""
        mock_jira_client.get_issue.return_value = create_mock_issue(
            status="Done",
            updated="2026-01-28T10:00:00.000+0000",
        )

        result = optimistic_validator.validate_with_timestamp(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            last_known_updated="2026-01-28T10:00:00+00:00",
        )

        assert result.valid is False
        assert "Status changed" in result.reason

    def test_timestamp_comparison_across_timezones(
        self, optimistic_validator, mock_jira_client
    ):
        """Timestamp comparison should work correctly across timezones."""
        # Jira returns UTC+0, last known was stored in different format
        mock_jira_client.get_issue.return_value = create_mock_issue(
            status="In Progress",
            updated="2026-01-28T10:00:00.000+0000",  # UTC
        )

        # Same instant, different timezone representation
        result = optimistic_validator.validate_with_timestamp(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            last_known_updated="2026-01-28T10:00:00Z",  # Z suffix
        )

        assert result.valid is True

    def test_pendulum_datetime_as_last_known(
        self, optimistic_validator, mock_jira_client
    ):
        """Should accept pendulum DateTime as last_known_updated."""
        mock_jira_client.get_issue.return_value = create_mock_issue(
            status="In Progress",
            updated="2026-01-28T10:00:00.000+0000",
        )

        last_known = pendulum.datetime(2026, 1, 28, 10, 0, 0, tz="UTC")

        result = optimistic_validator.validate_with_timestamp(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            last_known_updated=last_known,
        )

        assert result.valid is True


# =============================================================================
# API Error Handling Tests
# =============================================================================


class TestAPIErrorHandling:
    """Tests for handling Jira API errors gracefully."""

    def test_jira_404_returns_invalid_with_reason(
        self, pre_validator, mock_jira_client
    ):
        """When Jira returns 404, validation fails with descriptive error."""
        mock_jira_client.get_issue.side_effect = Exception(
            "Issue Does Not Exist"
        )

        result = pre_validator.validate_status("ESCRUM-999", "In Progress")

        assert result.valid is False
        assert "Jira API error" in result.reason
        assert "Issue Does Not Exist" in result.reason

    def test_jira_timeout_returns_invalid_with_reason(
        self, pre_validator, mock_jira_client
    ):
        """When Jira times out, validation fails with descriptive error."""
        mock_jira_client.get_issue.side_effect = Exception("Connection timeout")

        result = pre_validator.validate_status("ESCRUM-123", "In Progress")

        assert result.valid is False
        assert "Jira API error" in result.reason
        assert "timeout" in result.reason.lower()

    def test_sprint_membership_api_error(self, pre_validator, mock_jira_client):
        """When sprint check fails, validation fails with descriptive error."""
        mock_jira_client.is_issue_in_active_sprint.side_effect = Exception(
            "Service unavailable"
        )

        result = pre_validator.validate_sprint_membership("ESCRUM-123", expected_in_sprint=True)

        assert result.valid is False
        assert "Jira API error" in result.reason

    def test_optimistic_lock_api_error(
        self, optimistic_validator, mock_jira_client
    ):
        """When optimistic locking check fails, validation fails gracefully."""
        mock_jira_client.get_issue.side_effect = Exception("Rate limited")

        result = optimistic_validator.validate_with_timestamp(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            last_known_updated="2026-01-28T10:00:00+00:00",
        )

        assert result.valid is False
        assert "Jira API error" in result.reason


# =============================================================================
# Integration Tests (Multiple Validators)
# =============================================================================


class TestValidatorIntegration:
    """Integration tests combining multiple validation checks."""

    def test_full_validation_workflow(self, mock_jira_client):
        """Test complete validation workflow with both validators."""
        pre_validator = PreExecutionValidator(jira_client=mock_jira_client)
        optimistic_validator = OptimisticLockingValidator(jira_client=mock_jira_client)

        # Setup: ticket in expected state
        mock_jira_client.get_issue.return_value = create_mock_issue(
            status="In Progress",
            assignee_id="user-123",
            updated="2026-01-28T10:00:00.000+0000",
        )
        mock_jira_client.is_issue_in_active_sprint.return_value = True

        # Validate status
        status_result = pre_validator.validate_status("ESCRUM-123", "In Progress")
        assert status_result.valid is True

        # Validate sprint membership
        sprint_result = pre_validator.validate_sprint_membership(
            "ESCRUM-123", expected_in_sprint=True
        )
        assert sprint_result.valid is True

        # Validate assignee
        assignee_result = pre_validator.validate_assignee(
            "ESCRUM-123", expected_assignee_id="user-123"
        )
        assert assignee_result.valid is True

        # Validate with optimistic locking
        lock_result = optimistic_validator.validate_with_timestamp(
            ticket_key="ESCRUM-123",
            expected_status="In Progress",
            last_known_updated="2026-01-28T10:00:00+00:00",
        )
        assert lock_result.valid is True
