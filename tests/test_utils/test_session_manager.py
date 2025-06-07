"""Tests for session manager functions with YAML workflow support."""

import json

from src.dev_workflow_mcp.models.workflow_state import (
    DynamicWorkflowState,
    WorkflowItem,
)
from src.dev_workflow_mcp.models.yaml_workflow import (
    ExecutionConfig,
    WorkflowDefinition,
    WorkflowNode,
    WorkflowTree,
)
from src.dev_workflow_mcp.utils import session_manager


# Test Helper Functions
def create_test_workflow_def(name: str = "Test Workflow") -> WorkflowDefinition:
    """Create a test workflow definition for testing."""
    return WorkflowDefinition(
        name=name,
        description="Test workflow for unit tests",
        execution=ExecutionConfig(),
        workflow=WorkflowTree(
            goal="Test goal",
            root="start",
            tree={
                "start": WorkflowNode(
                    goal="Start the test",
                    acceptance_criteria={"completed": "Test started"},
                    next_allowed_nodes=["complete"],
                ),
                "complete": WorkflowNode(
                    goal="Complete the test",
                    acceptance_criteria={"finished": "Test completed"},
                    next_allowed_nodes=[],
                ),
            },
        ),
    )


def create_test_session(client_id: str, task_description: str) -> DynamicWorkflowState:
    """Create a test session directly for testing purposes."""
    workflow_def = create_test_workflow_def()
    return session_manager.create_dynamic_session(
        client_id, task_description, workflow_def
    )


class TestSessionManager:
    """Test session manager core functions."""

    def setup_method(self):
        """Clear sessions and reset services before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_create_dynamic_session(self):
        """Test creating a new dynamic session."""
        workflow_def = create_test_workflow_def()
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", workflow_def
        )

        assert session is not None
        assert session.client_id == "test-client"
        assert session.current_item == "Test task"
        assert session.workflow_name == "Test Workflow"
        assert session.current_node == "start"
        assert session.status == "READY"

    def test_get_session_exists(self):
        """Test getting an existing session."""
        original = create_test_session("test-client", "Test task")
        retrieved = session_manager.get_session(original.session_id)

        assert retrieved is not None
        assert retrieved.client_id == original.client_id
        assert retrieved.current_item == original.current_item

    def test_get_session_not_exists(self):
        """Test getting a non-existent session."""
        session = session_manager.get_session("non-existent")
        assert session is None

    def test_update_session(self):
        """Test updating session state."""
        original = create_test_session("test-client", "Test task")
        result = session_manager.update_session(
            original.session_id,
            status="RUNNING",
            current_item="Updated task",
        )
        assert result is True

        session = session_manager.get_session(original.session_id)
        assert session.status == "RUNNING"
        assert session.current_item == "Updated task"

    def test_update_session_not_exists(self):
        """Test updating a non-existent session."""
        result = session_manager.update_session("non-existent", status="RUNNING")
        assert result is False

    def test_export_session_to_markdown(self):
        """Test exporting session to markdown."""
        session = create_test_session("test-client", "Test task")
        markdown = session_manager.export_session_to_markdown(session.session_id)

        assert markdown is not None
        assert "# Dynamic Workflow State" in markdown
        assert "Test task" in markdown
        assert "Test Workflow" in markdown
        assert "start" in markdown

    def test_export_session_to_markdown_not_exists(self):
        """Test exporting non-existent session to markdown."""
        markdown = session_manager.export_session_to_markdown("non-existent")
        assert markdown is None


class TestSessionExportFunctions:
    """Test session export functions (JSON and format dispatch)."""

    def setup_method(self):
        """Clear sessions and reset services before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_export_session_to_json_basic(self):
        """Test basic JSON export functionality."""
        session = create_test_session("test-client", "Test task")
        json_str = session_manager.export_session_to_json(session.session_id)

        assert json_str is not None
        # Should be valid JSON
        data = json.loads(json_str)
        assert isinstance(data, dict)

    def test_export_session_to_json_structure(self):
        """Test JSON export returns expected structure."""
        session = create_test_session("test-client", "Test task")
        session_manager.update_session(
            session.session_id,
            status="RUNNING",
            current_item="Analysis task",
        )
        session_manager.add_log_to_session(session.session_id, "Test log entry")

        json_str = session_manager.export_session_to_json(session.session_id)
        data = json.loads(json_str)

        # Check top-level DynamicWorkflowState structure (flat JSON)
        assert "client_id" in data
        assert "workflow_name" in data
        assert "current_node" in data
        assert "status" in data
        assert "items" in data
        assert "log" in data

    def test_export_session_to_json_metadata_fields(self):
        """Test JSON export client identification fields."""
        session = create_test_session("test-client", "Test task")
        json_str = session_manager.export_session_to_json(session.session_id)
        data = json.loads(json_str)

        # Check client identification fields in flat structure
        assert "client_id" in data
        assert "created_at" in data
        assert "last_updated" in data
        assert data["client_id"] == "test-client"

    def test_export_session_to_json_state_fields(self):
        """Test JSON export state fields."""
        session = create_test_session("test-client", "Test task")
        session_manager.update_session(
            session.session_id,
            status="RUNNING",
            current_item="Current task",
        )

        json_str = session_manager.export_session_to_json(session.session_id)
        data = json.loads(json_str)

        # Check workflow state fields in flat structure
        assert data["workflow_name"] == "Test Workflow"
        assert data["status"] == "RUNNING"
        assert data["current_item"] == "Current task"

    def test_export_session_to_json_with_items(self):
        """Test JSON export includes items array."""
        session = create_test_session("test-client", "Test task")
        session.items = [
            WorkflowItem(id=1, description="Task 1", status="pending"),
            WorkflowItem(id=2, description="Task 2", status="completed"),
        ]

        json_str = session_manager.export_session_to_json(session.session_id)
        data = json.loads(json_str)

        items_data = data["items"]
        assert isinstance(items_data, list)
        assert len(items_data) == 2
        assert items_data[0]["description"] == "Task 1"
        assert items_data[1]["status"] == "completed"

    def test_export_session_to_json_not_exists(self):
        """Test JSON export for non-existent session."""
        json_str = session_manager.export_session_to_json("non-existent")
        assert json_str is None

    def test_export_session_format_dispatch_md(self):
        """Test export_session function dispatches to markdown for MD format."""
        session = create_test_session("test-client", "Test task")

        result = session_manager.export_session(session.session_id, "MD")

        assert result is not None
        assert "# Dynamic Workflow State" in result  # Markdown format
        assert not result.startswith("{")  # Not JSON

    def test_export_session_format_dispatch_json(self):
        """Test export_session function dispatches to JSON for JSON format."""
        session = create_test_session("test-client", "Test task")

        result = session_manager.export_session(session.session_id, "JSON")

        assert result is not None
        assert result.startswith("{")  # JSON format
        # Should be valid JSON
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_export_session_format_dispatch_case_insensitive(self):
        """Test export_session format parameter is case-insensitive."""
        session = create_test_session("test-client", "Test task")

        # Test lowercase
        md_result = session_manager.export_session(session.session_id, "md")
        json_result = session_manager.export_session(session.session_id, "json")

        assert md_result is not None
        assert "# Dynamic Workflow State" in md_result

        assert json_result is not None
        assert json_result.startswith("{")

    def test_export_session_format_dispatch_invalid_format(self):
        """Test export_session with invalid format defaults to markdown."""
        session = create_test_session("test-client", "Test task")

        result = session_manager.export_session(session.session_id, "INVALID")

        assert result is not None
        assert "# Dynamic Workflow State" in result  # Should default to markdown

    def test_export_session_format_dispatch_not_exists(self):
        """Test export_session for non-existent session."""
        result = session_manager.export_session("non-existent", "MD")
        assert result is None

    def test_export_session_json_complete_data_integrity(self):
        """Test complete data integrity for JSON export."""
        session = create_test_session("complex-client", "Complex task")

        # Add some data to test
        session_manager.add_log_to_session(session.session_id, "First log entry")
        session_manager.add_log_to_session(session.session_id, "Second log entry")
        session_manager.add_item_to_session(session.session_id, "Additional task")

        json_str = session_manager.export_session_to_json(session.session_id)
        data = json.loads(json_str)

        # Verify flat DynamicWorkflowState structure
        assert "client_id" in data
        assert "workflow_name" in data
        assert "current_node" in data
        assert "status" in data
        assert "items" in data
        assert "log" in data

        # Verify data integrity in flat structure
        assert data["client_id"] == "complex-client"
        assert data["workflow_name"] == "Test Workflow"
        assert len(data["items"]) == 1  # Added item (sessions start with empty items)
        assert len(data["log"]) >= 2  # 2 added log entries

    def test_export_session_format_consistency(self):
        """Test that export format is consistent between calls."""
        session = create_test_session("test-client", "Test task")

        # Multiple calls should return consistent format
        md1 = session_manager.export_session(session.session_id, "MD")
        md2 = session_manager.export_session(session.session_id, "MD")
        json1 = session_manager.export_session(session.session_id, "JSON")
        json2 = session_manager.export_session(session.session_id, "JSON")

        assert md1 == md2
        assert json1 == json2
        assert md1 != json1  # Different formats should be different
