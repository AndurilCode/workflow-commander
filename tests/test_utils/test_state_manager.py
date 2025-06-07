"""Tests for StateManager with YAML-only architecture."""

import os
from unittest.mock import patch

from src.dev_workflow_mcp.utils import session_manager
from src.dev_workflow_mcp.utils.state_manager import (
    StateManager,
    get_file_operation_instructions,
)


class TestStateManager:
    """Test StateManager initialization and basic functions."""

    def setup_method(self):
        """Set up test environment."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()

    def test_init_default(self):
        """Test StateManager initialization with defaults."""
        manager = StateManager()
        assert manager.client_id == "default"

    def test_init_custom_client(self):
        """Test StateManager initialization with custom client ID."""
        manager = StateManager(client_id="custom-client")
        assert manager.client_id == "custom-client"

    def test_create_initial_state_no_workflows(self):
        """Test creating initial state when no workflows are available."""
        manager = StateManager(client_id="test-init-client")
        manager.create_initial_state("Test initialization task")

        # Should not create session since no workflows available
        result = manager.read_state()
        assert result is None

    def test_read_state_no_session(self):
        """Test reading state when no session exists."""
        manager = StateManager(client_id="test-read-client")
        result = manager.read_state()

        # Should return None since no session exists
        assert result is None

    def test_update_state_section_legacy_not_supported(self):
        """Test that legacy state section updates are no longer supported."""
        manager = StateManager(client_id="test-update-client")

        # Legacy update_state_section returns False (YAML-only architecture)
        result = manager.update_state_section("ANALYZE", "RUNNING", "New task")
        assert result is False

    def test_update_state_section_no_current_item(self):
        """Test state section update with None current_item (not supported)."""
        manager = StateManager(client_id="test-null-client")

        result = manager.update_state_section("ANALYZE", "RUNNING", None)
        assert result is False

    def test_update_state_section_creates_session(self):
        """Test state section update fails to create session (YAML-only)."""
        manager = StateManager(client_id="test-auto-create-client")
        result = manager.update_state_section("ANALYZE", "RUNNING", "Task")

        # Should fail in YAML-only architecture
        assert result is False

    def test_update_state_section_invalid_phase(self):
        """Test state section update with invalid phase."""
        manager = StateManager(client_id="test-invalid-client")
        result = manager.update_state_section("INVALID", "RUNNING", "Task")

        # Should fail with invalid phase
        assert result is False

    def test_update_state_section_invalid_status(self):
        """Test state section update with invalid status."""
        manager = StateManager(client_id="test-invalid-status-client")
        result = manager.update_state_section("ANALYZE", "INVALID", "Task")

        # Should fail with invalid status
        assert result is False

    def test_append_to_log_no_session(self):
        """Test log entry append when no session exists."""
        manager = StateManager(client_id="test-log-client")

        # Should fail if no session exists
        result = manager.append_to_log("New log entry")
        assert result is False

    def test_append_to_log_creates_session(self):
        """Test log append fails to create session (YAML-only)."""
        manager = StateManager(client_id="test-log-create-client")
        result = manager.append_to_log("New entry")

        # Should fail in YAML-only architecture
        assert result is False

    def test_client_id_operations(self):
        """Test client ID getter and setter."""
        manager = StateManager(client_id="original-client")
        assert manager.get_client_id() == "original-client"

        manager.set_client_id("new-client")
        assert manager.get_client_id() == "new-client"

    def test_session_isolation_no_sessions(self):
        """Test that different clients have isolated (empty) sessions."""
        manager1 = StateManager(client_id="client-1")
        manager2 = StateManager(client_id="client-2")

        # Try to create different tasks (will fail - no workflows)
        manager1.create_initial_state("Task for client 1")
        manager2.create_initial_state("Task for client 2")

        # Both should return None (no sessions created)
        content1 = manager1.read_state()
        content2 = manager2.read_state()

        assert content1 is None
        assert content2 is None

    def test_multiple_log_entries_no_session(self):
        """Test multiple log entries fail when no session exists."""
        manager = StateManager(client_id="test-multi-log-client")

        # All log operations should fail without a session
        result1 = manager.append_to_log("First entry")
        result2 = manager.append_to_log("Second entry")
        result3 = manager.append_to_log("Third entry")

        assert result1 is False
        assert result2 is False
        assert result3 is False


class TestStateManagerCompatibility:
    """Test StateManager backward compatibility features."""

    def setup_method(self):
        """Clear session state before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()

    def test_constructor_api_simplification(self):
        """Test that constructor API has been simplified to only require client_id."""
        # New simplified way: StateManager(client_id=client_id)
        manager = StateManager(client_id="new-client")
        assert manager.client_id == "new-client"

        # Default behavior
        manager_default = StateManager()
        assert manager_default.client_id == "default"


class TestGetFileOperationInstructions:
    """Test get_file_operation_instructions function with format support."""

    def setup_method(self):
        """Clear sessions before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()

    @patch.dict(os.environ, {"WORKFLOW_LOCAL_STATE_FILE": "false"})
    def test_get_file_operation_instructions_disabled(self):
        """Test get_file_operation_instructions when local state file is disabled."""
        result = get_file_operation_instructions()
        assert result == ""

    def test_get_file_operation_instructions_no_session(self):
        """Test get_file_operation_instructions returns empty when no session."""
        result = get_file_operation_instructions("default")
        assert result == ""

    # Note: Other file operation tests that required legacy session creation have been removed.
    # The functionality still works but requires proper YAML workflow sessions which are
    # tested in integration tests.
