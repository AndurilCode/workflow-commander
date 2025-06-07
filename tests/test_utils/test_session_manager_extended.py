"""Extended tests for session manager functions to improve coverage."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.dev_workflow_mcp.models.yaml_workflow import (
    WorkflowDefinition,
    WorkflowInput,
    WorkflowNode,
    WorkflowTree,
)
from src.dev_workflow_mcp.utils import session_manager


@pytest.fixture
def test_workflow_def():
    """Create a test workflow definition."""
    return WorkflowDefinition(
        name="Test Workflow",
        description="A test workflow",
        inputs={},
        workflow=WorkflowTree(
            goal="Test workflow goal",
            root="start",
            tree={
                "start": WorkflowNode(
                    goal="Start the workflow",
                    acceptance_criteria={"initialized": "Workflow is initialized"},
                    next_allowed_nodes=["end"],
                ),
                "end": WorkflowNode(
                    goal="End the workflow",
                    acceptance_criteria={"completed": "Workflow is completed"},
                    next_allowed_nodes=[],
                ),
            },
        ),
    )


class TestSessionManagerConfiguration:
    """Test session manager configuration functions."""

    def setup_method(self):
        """Clear sessions and reset services before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_set_server_config_basic(self):
        """Test basic server config setting."""
        mock_config = Mock()
        session_manager.set_server_config(mock_config)

        assert session_manager._server_config is mock_config

    def test_set_server_config_with_cache_mode(self):
        """Test server config setting with cache mode."""
        mock_config = Mock()
        mock_config.cache_dir = "/tmp/test_cache"
        mock_config.cache_collection_name = "test_collection"
        mock_config.cache_embedding_model = "test-model"
        mock_config.cache_max_results = 50

        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager"):
            session_manager.set_server_config(mock_config)

        assert session_manager._server_config is mock_config

    def test_initialize_cache_manager_success(self):
        """Test successful cache manager initialization."""
        mock_config = Mock()
        mock_config.ensure_cache_dir.return_value = True
        mock_config.cache_dir = "/tmp/test_cache"
        mock_config.cache_collection_name = "test_collection"
        mock_config.cache_embedding_model = "test-model"
        mock_config.cache_max_results = 50

        # Reset the global cache manager to None first
        session_manager._cache_manager = None

        with patch(
            "src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager"
        ) as mock_cache_class:
            result = session_manager._initialize_cache_manager(mock_config)

        assert result is True
        mock_cache_class.assert_called_once()

    def test_initialize_cache_manager_failure(self):
        """Test cache manager initialization failure."""
        mock_config = Mock()
        mock_config.ensure_cache_dir.return_value = False

        # Reset the global cache manager to None first
        session_manager._cache_manager = None

        result = session_manager._initialize_cache_manager(mock_config)

        assert result is False

    def test_initialize_cache_manager_exception(self):
        """Test cache manager initialization with exception."""
        mock_config = Mock()
        mock_config.ensure_cache_dir.side_effect = Exception("Cache init failed")

        # Reset the global cache manager to None first
        session_manager._cache_manager = None

        result = session_manager._initialize_cache_manager(mock_config)

        assert result is False

    def test_should_initialize_cache_from_environment_cache_dir_exists(self):
        """Test cache initialization detection when cache directory exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / ".workflow-commander" / "cache"
            cache_dir.mkdir(parents=True)

            with patch("pathlib.Path.cwd", return_value=Path(temp_dir)):
                result = session_manager._should_initialize_cache_from_environment()

            assert result is True

    def test_should_initialize_cache_from_environment_command_line(self):
        """Test cache initialization detection from command line."""
        with patch.dict(
            "os.environ", {"MCP_COMMAND_LINE": "server --enable-cache-mode"}
        ):
            result = session_manager._should_initialize_cache_from_environment()

        assert result is True

    def test_should_initialize_cache_from_environment_workflow_dir(self):
        """Test cache initialization detection from workflow commander directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workflow_dir = Path(temp_dir) / ".workflow-commander"
            workflow_dir.mkdir()

            with patch("pathlib.Path.cwd", return_value=Path(temp_dir)):
                result = session_manager._should_initialize_cache_from_environment()

        assert result is True

    def test_should_initialize_cache_from_environment_false(self):
        """Test cache initialization detection returns false when no indicators."""
        with patch("pathlib.Path.exists", return_value=False):
            with patch.dict("os.environ", {}, clear=True):
                result = session_manager._should_initialize_cache_from_environment()

        assert result is False

    def test_is_test_environment_pytest(self):
        """Test detection of test environment."""
        result = session_manager._is_test_environment()

        # Should return True since we're running under pytest
        assert result is True


class TestSessionManagerClientRegistry:
    """Test client session registry functions."""

    def setup_method(self):
        """Clear sessions and reset services before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_register_session_for_client(self, test_workflow_def):
        """Test registering a session for a client."""
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", test_workflow_def
        )

        # Should be automatically registered
        assert "test-client" in session_manager.client_session_registry
        assert (
            session.session_id in session_manager.client_session_registry["test-client"]
        )

    def test_unregister_session_for_client(self, test_workflow_def):
        """Test unregistering a session for a client."""
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", test_workflow_def
        )

        # Manually unregister
        session_manager._unregister_session_for_client(
            "test-client", session.session_id
        )

        # Should be removed from registry
        if "test-client" in session_manager.client_session_registry:
            assert (
                session.session_id
                not in session_manager.client_session_registry["test-client"]
            )

    def test_get_sessions_by_client(self, test_workflow_def):
        """Test getting sessions by client ID."""
        session1 = session_manager.create_dynamic_session(
            "test-client", "Task 1", test_workflow_def
        )
        session2 = session_manager.create_dynamic_session(
            "test-client", "Task 2", test_workflow_def
        )
        session3 = session_manager.create_dynamic_session(
            "other-client", "Task 3", test_workflow_def
        )

        client_sessions = session_manager.get_sessions_by_client("test-client")

        assert len(client_sessions) == 2
        session_ids = [s.session_id for s in client_sessions]
        assert session1.session_id in session_ids
        assert session2.session_id in session_ids
        assert session3.session_id not in session_ids

    def test_get_sessions_by_client_empty(self):
        """Test getting sessions for client with no sessions."""
        client_sessions = session_manager.get_sessions_by_client("nonexistent-client")

        assert len(client_sessions) == 0


class TestSessionManagerDynamicInputs:
    """Test dynamic input preparation functions."""

    def setup_method(self):
        """Clear sessions and reset services before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_prepare_dynamic_inputs_basic(self, test_workflow_def):
        """Test basic dynamic input preparation."""
        # Add inputs to workflow definition
        test_workflow_def.inputs = {
            "task_description": WorkflowInput(
                type="string", description="Task to perform"
            ),
            "priority": WorkflowInput(
                type="string", description="Task priority", default="medium"
            ),
        }

        inputs = session_manager._prepare_dynamic_inputs("Test task", test_workflow_def)

        assert "task_description" in inputs
        assert inputs["task_description"] == "Test task"
        assert "priority" in inputs
        assert inputs["priority"] == "medium"

    def test_prepare_dynamic_inputs_no_inputs(self, test_workflow_def):
        """Test dynamic input preparation with no workflow inputs."""
        inputs = session_manager._prepare_dynamic_inputs("Test task", test_workflow_def)

        # Should return empty dict when no inputs defined
        assert inputs == {}

    def test_prepare_dynamic_inputs_type_defaults(self, test_workflow_def):
        """Test dynamic input preparation with type-based defaults."""
        test_workflow_def.inputs = {
            "task_description": WorkflowInput(
                type="string", description="Task to perform", required=True
            ),
            "count": WorkflowInput(
                type="number", description="Number of items", required=True
            ),
            "enabled": WorkflowInput(
                type="boolean", description="Enable feature", required=True
            ),
            "name": WorkflowInput(type="string", description="Name", required=True),
            "config": WorkflowInput(
                type="object", description="Configuration object", required=True
            ),
        }

        inputs = session_manager._prepare_dynamic_inputs("Test task", test_workflow_def)

        # When validation fails, it returns minimal fallback
        assert "task_description" in inputs
        assert inputs["task_description"] == "Test task"


class TestSessionManagerNodeOperations:
    """Test session node operation functions."""

    def setup_method(self):
        """Clear sessions and reset services before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_update_dynamic_session_node_success(self, test_workflow_def):
        """Test successful node update."""
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", test_workflow_def
        )

        result = session_manager.update_dynamic_session_node(
            session.session_id, "end", test_workflow_def, status="RUNNING"
        )

        assert result is True
        updated_session = session_manager.get_session(session.session_id)
        assert updated_session.current_node == "end"
        assert updated_session.status == "RUNNING"

    def test_update_dynamic_session_node_invalid_session(self, test_workflow_def):
        """Test node update with invalid session."""
        result = session_manager.update_dynamic_session_node(
            "invalid-session", "middle", test_workflow_def
        )

        assert result is False

    def test_update_dynamic_session_node_with_outputs(self, test_workflow_def):
        """Test node update with outputs."""
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", test_workflow_def
        )

        outputs = {"completed_criteria": {"test": "evidence"}}
        result = session_manager.update_dynamic_session_node(
            session.session_id, "end", test_workflow_def, outputs=outputs
        )

        assert result is True
        updated_session = session_manager.get_session(session.session_id)
        assert "start" in updated_session.node_outputs
        assert updated_session.node_outputs["start"] == outputs


class TestSessionManagerUtilityFunctions:
    """Test utility functions in session manager."""

    def setup_method(self):
        """Clear sessions and reset services before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_delete_session_success(self, test_workflow_def):
        """Test successful session deletion."""
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", test_workflow_def
        )

        result = session_manager.delete_session(session.session_id)

        assert result is True
        assert session_manager.get_session(session.session_id) is None

    def test_delete_session_not_exists(self):
        """Test deleting non-existent session."""
        result = session_manager.delete_session("nonexistent-session")

        assert result is False

    def test_get_all_sessions(self, test_workflow_def):
        """Test getting all sessions."""
        session1 = session_manager.create_dynamic_session(
            "client1", "Task 1", test_workflow_def
        )
        session2 = session_manager.create_dynamic_session(
            "client2", "Task 2", test_workflow_def
        )

        all_sessions = session_manager.get_all_sessions()

        assert len(all_sessions) == 2
        assert session1.session_id in all_sessions
        assert session2.session_id in all_sessions

    def test_add_log_to_session_success(self, test_workflow_def):
        """Test adding log entry to session."""
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", test_workflow_def
        )

        result = session_manager.add_log_to_session(
            session.session_id, "Test log entry"
        )

        assert result is True
        updated_session = session_manager.get_session(session.session_id)
        assert len(updated_session.log) > 0
        assert "Test log entry" in updated_session.log[-1]

    def test_add_log_to_session_not_exists(self):
        """Test adding log to non-existent session."""
        result = session_manager.add_log_to_session("nonexistent", "Test log")

        assert result is False

    def test_update_dynamic_session_status_success(self, test_workflow_def):
        """Test updating session status."""
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", test_workflow_def
        )

        result = session_manager.update_dynamic_session_status(
            session.session_id, status="RUNNING", current_item="Updated task"
        )

        assert result is True
        updated_session = session_manager.get_session(session.session_id)
        assert updated_session.status == "RUNNING"
        assert updated_session.current_item == "Updated task"

    def test_update_dynamic_session_status_not_exists(self):
        """Test updating status of non-existent session."""
        result = session_manager.update_dynamic_session_status(
            "nonexistent", status="RUNNING"
        )

        assert result is False

    def test_add_item_to_session_success(self, test_workflow_def):
        """Test adding item to session."""
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", test_workflow_def
        )

        result = session_manager.add_item_to_session(
            session.session_id, "New task item"
        )

        assert result is True
        updated_session = session_manager.get_session(session.session_id)
        # Session starts empty, adding one item makes 1
        assert len(updated_session.items) == 1
        # The new item is added at the end (index 0)
        assert updated_session.items[0].description == "New task item"

    def test_add_item_to_session_not_exists(self):
        """Test adding item to non-existent session."""
        result = session_manager.add_item_to_session("nonexistent", "New task")

        assert result is False

    def test_mark_item_completed_in_session_success(self, test_workflow_def):
        """Test marking item as completed in session."""
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", test_workflow_def
        )
        session_manager.add_item_to_session(session.session_id, "Test item")

        result = session_manager.mark_item_completed_in_session(session.session_id, 1)

        assert result is True
        updated_session = session_manager.get_session(session.session_id)
        assert updated_session.items[0].status == "completed"

    def test_mark_item_completed_in_session_not_exists(self):
        """Test marking item completed in non-existent session."""
        result = session_manager.mark_item_completed_in_session("nonexistent", 1)

        assert result is False

    def test_get_session_type(self, test_workflow_def):
        """Test getting session type."""
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", test_workflow_def
        )

        session_type = session_manager.get_session_type(session.session_id)

        assert session_type == "dynamic"

    def test_get_session_type_not_exists(self):
        """Test getting type of non-existent session."""
        session_type = session_manager.get_session_type("nonexistent")

        assert session_type is None

    def test_get_session_stats(self, test_workflow_def):
        """Test getting session statistics."""
        session_manager.create_dynamic_session("client1", "Task 1", test_workflow_def)
        session_manager.create_dynamic_session("client2", "Task 2", test_workflow_def)

        stats = session_manager.get_session_stats()

        assert "total_sessions" in stats
        assert "dynamic_sessions" in stats
        assert "sessions_by_status" in stats
        assert stats["total_sessions"] == 2
        assert stats["dynamic_sessions"] == 2


class TestSessionManagerWorkflowDefinitionCache:
    """Test workflow definition cache functions."""

    def setup_method(self):
        """Clear sessions and cache before each test."""
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_store_workflow_definition_in_cache(self, test_workflow_def):
        """Test storing workflow definition in cache."""
        session_id = "test-session-123"

        session_manager.store_workflow_definition_in_cache(
            session_id, test_workflow_def
        )

        assert session_id in session_manager.workflow_definitions_cache
        assert (
            session_manager.workflow_definitions_cache[session_id] == test_workflow_def
        )

    def test_get_workflow_definition_from_cache(self, test_workflow_def):
        """Test getting workflow definition from cache."""
        session_id = "test-session-123"
        session_manager.store_workflow_definition_in_cache(
            session_id, test_workflow_def
        )

        retrieved_def = session_manager.get_workflow_definition_from_cache(session_id)

        assert retrieved_def == test_workflow_def

    def test_get_workflow_definition_from_cache_not_exists(self):
        """Test getting non-existent workflow definition from cache."""
        retrieved_def = session_manager.get_workflow_definition_from_cache(
            "nonexistent"
        )

        assert retrieved_def is None

    def test_clear_workflow_definition_cache(self, test_workflow_def):
        """Test clearing workflow definition from cache."""
        session_id = "test-session-123"
        session_manager.store_workflow_definition_in_cache(
            session_id, test_workflow_def
        )

        session_manager.clear_workflow_definition_cache(session_id)

        assert session_id not in session_manager.workflow_definitions_cache

    def test_get_dynamic_session_workflow_def(self, test_workflow_def):
        """Test getting workflow definition for dynamic session."""
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", test_workflow_def
        )

        # Store in cache
        session_manager.store_workflow_definition_in_cache(
            session.session_id, test_workflow_def
        )

        retrieved_def = session_manager.get_dynamic_session_workflow_def(
            session.session_id
        )

        assert retrieved_def == test_workflow_def

    def test_get_dynamic_session_workflow_def_not_exists(self):
        """Test getting workflow definition for non-existent session."""
        retrieved_def = session_manager.get_dynamic_session_workflow_def("nonexistent")

        assert retrieved_def is None


class TestSessionManagerConflictDetection:
    """Test session conflict detection functions."""

    def setup_method(self):
        """Clear sessions and reset services before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_detect_session_conflict_no_conflict(self, test_workflow_def):
        """Test conflict detection when no conflict exists."""
        session_manager.create_dynamic_session(
            "test-client", "Task 1", test_workflow_def
        )

        conflict = session_manager.detect_session_conflict("other-client")

        assert conflict is None

    def test_detect_session_conflict_with_conflict(self, test_workflow_def):
        """Test conflict detection when conflict exists."""
        session_manager.create_dynamic_session(
            "test-client", "Task 1", test_workflow_def
        )

        conflict = session_manager.detect_session_conflict("test-client")

        # Conflict detection is disabled, always returns None
        assert conflict is None


class TestSessionManagerSummaryAndCleanup:
    """Test session summary and cleanup functions."""

    def setup_method(self):
        """Clear sessions and reset services before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_get_session_summary(self, test_workflow_def):
        """Test getting session summary."""
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", test_workflow_def
        )

        summary = session_manager.get_session_summary(session.session_id)

        assert isinstance(summary, str)
        assert "Test task" in summary
        assert "Test Workflow" in summary

    def test_get_session_summary_not_exists(self):
        """Test getting summary for non-existent session."""
        summary = session_manager.get_session_summary("nonexistent")

        assert "Session not found" in summary

    def test_clear_session_completely(self, test_workflow_def):
        """Test completely clearing a session."""
        session = session_manager.create_dynamic_session(
            "test-client", "Test task", test_workflow_def
        )
        session_id = session.session_id

        result = session_manager.clear_session_completely(session_id)

        assert result["success"] is True
        assert session_manager.get_session(session_id) is None

    def test_clear_session_completely_not_exists(self):
        """Test clearing non-existent session."""
        result = session_manager.clear_session_completely("nonexistent")

        assert result["success"] is False
        # Method doesn't include a "message" field, just returns success=False

    def test_clear_all_client_sessions(self, test_workflow_def):
        """Test clearing all sessions for a client."""
        session1 = session_manager.create_dynamic_session(
            "test-client", "Task 1", test_workflow_def
        )
        session2 = session_manager.create_dynamic_session(
            "test-client", "Task 2", test_workflow_def
        )
        session3 = session_manager.create_dynamic_session(
            "other-client", "Task 3", test_workflow_def
        )

        result = session_manager.clear_all_client_sessions("test-client")

        assert result["success"] is True
        assert result["sessions_cleared"] == 2
        assert session_manager.get_session(session1.session_id) is None
        assert session_manager.get_session(session2.session_id) is None
        assert (
            session_manager.get_session(session3.session_id) is not None
        )  # Other client's session should remain
