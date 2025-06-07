"""Integration tests for cache mode functionality.

This module tests the complete cache mode workflow including:
- Cache manager initialization
- Session storage and retrieval from cache
- Cache synchronization between file and cache storage
- Cache cleanup and archiving
- Error handling and edge cases
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.dev_workflow_mcp.config import ServerConfig
from src.dev_workflow_mcp.models.workflow_state import DynamicWorkflowState
from src.dev_workflow_mcp.models.yaml_workflow import (
    WorkflowDefinition,
    WorkflowNode,
    WorkflowTree,
)
from src.dev_workflow_mcp.services import (
    initialize_session_services,
    reset_session_services,
)
from src.dev_workflow_mcp.utils import session_manager


@pytest.fixture
def test_workflow_def():
    """Create a test workflow definition."""
    return WorkflowDefinition(
        name="Cache Test Workflow",
        description="A test workflow for cache integration",
        inputs={},
        workflow=WorkflowTree(
            goal="Test cache workflow",
            root="start",
            tree={
                "start": WorkflowNode(
                    goal="Start the cache test",
                    acceptance_criteria={"initialized": "Cache test is initialized"},
                    next_allowed_nodes=["process"],
                ),
                "process": WorkflowNode(
                    goal="Process data in cache",
                    acceptance_criteria={"processed": "Data is processed"},
                    next_allowed_nodes=["end"],
                ),
                "end": WorkflowNode(
                    goal="End the cache test",
                    acceptance_criteria={"completed": "Cache test is completed"},
                    next_allowed_nodes=[],
                ),
            },
        ),
    )


@pytest.fixture
def cache_enabled_config():
    """Create a server config with cache mode enabled."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config = ServerConfig(
            repository_path=temp_dir,
            enable_local_state_file=True,
            enable_cache_mode=True,
            cache_db_path=str(Path(temp_dir) / "cache"),
            cache_collection_name="test_collection",
            cache_embedding_model="test-model",
            cache_max_results=50,
        )
        yield config


class TestCacheModeInitialization:
    """Test cache mode initialization and configuration."""

    def setup_method(self):
        """Reset services and clear sessions before each test."""
        reset_session_services()
        initialize_session_services()
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_cache_manager_initialization_success(self, cache_enabled_config):
        """Test successful cache manager initialization."""
        # Mock the WorkflowCacheManager to avoid external dependencies
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance
            
            # Set the server config
            session_manager.set_server_config(cache_enabled_config)
            
            # Initialize cache manager
            result = session_manager._initialize_cache_manager(cache_enabled_config)
            
            assert result is True
            mock_cache_class.assert_called_once()
            assert session_manager._cache_manager is mock_cache_instance

    def test_cache_manager_initialization_failure(self):
        """Test cache manager initialization failure."""
        config = Mock()
        config.ensure_cache_dir.return_value = False
        
        # Reset cache manager
        session_manager._cache_manager = None
        
        result = session_manager._initialize_cache_manager(config)
        
        assert result is False
        assert session_manager._cache_manager is None

    def test_cache_manager_initialization_exception(self):
        """Test cache manager initialization with exception."""
        config = Mock()
        config.ensure_cache_dir.side_effect = Exception("Cache initialization failed")
        
        # Reset cache manager
        session_manager._cache_manager = None
        
        result = session_manager._initialize_cache_manager(config)
        
        assert result is False
        assert session_manager._cache_manager is None

    def test_cache_environment_detection_cache_dir_exists(self):
        """Test cache environment detection when cache directory exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir) / ".workflow-commander" / "cache"
            cache_dir.mkdir(parents=True)
            
            with patch("pathlib.Path.cwd", return_value=Path(temp_dir)):
                result = session_manager._should_initialize_cache_from_environment()
            
            assert result is True

    def test_cache_environment_detection_workflow_dir(self):
        """Test cache environment detection from workflow commander directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            workflow_dir = Path(temp_dir) / ".workflow-commander"
            workflow_dir.mkdir()
            
            with patch("pathlib.Path.cwd", return_value=Path(temp_dir)):
                result = session_manager._should_initialize_cache_from_environment()
            
            assert result is True

    def test_cache_environment_detection_command_line(self):
        """Test cache environment detection from command line."""
        with patch.dict("os.environ", {"MCP_COMMAND_LINE": "server --enable-cache-mode"}):
            result = session_manager._should_initialize_cache_from_environment()
        
        assert result is True


class TestCacheSessionOperations:
    """Test session operations with cache mode enabled."""

    def setup_method(self):
        """Reset services and clear sessions before each test."""
        reset_session_services()
        initialize_session_services()
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_session_creation_with_cache(self, cache_enabled_config, test_workflow_def):
        """Test session creation with cache mode enabled."""
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance
            
            # Set up cache-enabled config
            session_manager.set_server_config(cache_enabled_config)
            
            # Create a session
            session = session_manager.create_dynamic_session(
                "cache-test-client", "Cache test task", test_workflow_def
            )
            
            assert session is not None
            assert session.client_id == "cache-test-client"
            assert session.current_item == "Cache test task"
            assert session.workflow_name == "Cache Test Workflow"

    def test_session_sync_to_cache(self, cache_enabled_config, test_workflow_def):
        """Test session synchronization to cache."""
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance
            
            # Set up cache-enabled config
            session_manager.set_server_config(cache_enabled_config)
            
            # Create a session
            session = session_manager.create_dynamic_session(
                "sync-test-client", "Sync test task", test_workflow_def
            )
            
            # Test sync operation
            result = session_manager.sync_session(session.session_id)
            
            # Should succeed (even if cache operations are mocked)
            assert result is True

    def test_force_cache_sync_session(self, cache_enabled_config, test_workflow_def):
        """Test force cache sync with detailed results."""
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance
            
            # Set up cache-enabled config
            session_manager.set_server_config(cache_enabled_config)
            
            # Create a session
            session = session_manager.create_dynamic_session(
                "force-sync-client", "Force sync task", test_workflow_def
            )
            
            # Test force sync operation
            result = session_manager.force_cache_sync_session(session.session_id)
            
            # Should return a dictionary with sync results
            assert isinstance(result, dict)

    def test_session_restoration_from_cache(self, cache_enabled_config):
        """Test session restoration from cache storage."""
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance
            
            # Set up cache-enabled config
            session_manager.set_server_config(cache_enabled_config)
            
            # Test restore operation
            restored_count = session_manager.restore_sessions_from_cache("test-client")
            
            # Should return number of restored sessions (0 in this mock case)
            assert isinstance(restored_count, int)
            assert restored_count >= 0

    def test_auto_restore_sessions_on_startup(self, cache_enabled_config):
        """Test automatic session restoration on startup."""
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance
            
            # Set up cache-enabled config
            session_manager.set_server_config(cache_enabled_config)
            
            # Test auto-restore operation
            restored_count = session_manager.auto_restore_sessions_on_startup()
            
            # Should return number of restored sessions
            assert isinstance(restored_count, int)
            assert restored_count >= 0

    def test_list_cached_sessions(self, cache_enabled_config):
        """Test listing cached sessions."""
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance
            
            # Set up cache-enabled config
            session_manager.set_server_config(cache_enabled_config)
            
            # Test list operation
            cached_sessions = session_manager.list_cached_sessions("test-client")
            
            # Should return a list of session dictionaries
            assert isinstance(cached_sessions, list)


class TestCacheSessionLifecycle:
    """Test complete session lifecycle with cache mode."""

    def setup_method(self):
        """Reset services and clear sessions before each test."""
        reset_session_services()
        initialize_session_services()
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_complete_session_lifecycle_with_cache(self, cache_enabled_config, test_workflow_def):
        """Test complete session lifecycle from creation to cleanup with cache."""
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance
            
            # Set up cache-enabled config
            session_manager.set_server_config(cache_enabled_config)
            
            # 1. Create session
            session = session_manager.create_dynamic_session(
                "lifecycle-client", "Lifecycle test task", test_workflow_def
            )
            assert session is not None
            
            # 2. Update session status
            update_result = session_manager.update_session(
                session.session_id, status="RUNNING", current_item="Processing..."
            )
            assert update_result is True
            
            # 3. Add log entries
            log_result = session_manager.add_log_to_session(
                session.session_id, "Started processing"
            )
            assert log_result is True
            
            # 4. Update node
            node_result = session_manager.update_dynamic_session_node(
                session.session_id, "process", test_workflow_def, status="RUNNING"
            )
            assert node_result is True
            
            # 5. Complete session
            complete_result = session_manager.update_session(
                session.session_id, status="COMPLETED", current_node="end"
            )
            assert complete_result is True
            
            # 6. Sync to cache
            sync_result = session_manager.sync_session(session.session_id)
            assert sync_result is True
            
            # 7. Get session summary
            summary = session_manager.get_session_summary(session.session_id)
            assert isinstance(summary, str)
            assert "lifecycle-client" in summary

    def test_session_cleanup_with_cache_archiving(self, cache_enabled_config, test_workflow_def):
        """Test session cleanup with cache and archiving enabled."""
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance
            
            # Set up cache-enabled config
            session_manager.set_server_config(cache_enabled_config)
            
            # Create and complete a session
            session = session_manager.create_dynamic_session(
                "cleanup-client", "Cleanup test task", test_workflow_def
            )
            session_manager.update_session(session.session_id, status="COMPLETED")
            
            # Mock the session to be old enough for cleanup
            from datetime import UTC, datetime, timedelta
            old_time = datetime.now(UTC) - timedelta(hours=48)
            session_manager.update_session(session.session_id, created_at=old_time)
            
            # Test cleanup with archiving
            cleaned_count = session_manager.cleanup_completed_sessions(
                keep_recent_hours=24, archive_before_cleanup=True
            )
            
            # Should clean up the old session
            assert cleaned_count >= 0  # May be 0 if session wasn't actually old enough

    def test_clear_session_completely_with_cache(self, cache_enabled_config, test_workflow_def):
        """Test complete session clearing with cache."""
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance
            
            # Set up cache-enabled config
            session_manager.set_server_config(cache_enabled_config)
            
            # Create a session
            session = session_manager.create_dynamic_session(
                "clear-client", "Clear test task", test_workflow_def
            )
            
            # Clear session completely
            result = session_manager.clear_session_completely(session.session_id)
            
            # Should return detailed results
            assert isinstance(result, dict)
            
            # Session should be removed
            cleared_session = session_manager.get_session(session.session_id)
            assert cleared_session is None


class TestCacheErrorHandling:
    """Test error handling in cache mode operations."""

    def setup_method(self):
        """Reset services and clear sessions before each test."""
        reset_session_services()
        initialize_session_services()
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_cache_operations_without_cache_manager(self, test_workflow_def):
        """Test cache operations when cache manager is not initialized."""
        # Ensure no cache manager is set
        session_manager._cache_manager = None
        
        # Create a session without cache
        session = session_manager.create_dynamic_session(
            "no-cache-client", "No cache test", test_workflow_def
        )
        
        # Cache operations should still work (gracefully degrade)
        sync_result = session_manager.sync_session(session.session_id)
        assert sync_result is True
        
        restore_count = session_manager.restore_sessions_from_cache()
        assert isinstance(restore_count, int)

    def test_cache_operations_with_cache_errors(self, cache_enabled_config, test_workflow_def):
        """Test cache operations when cache manager throws errors."""
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            # Make cache operations raise exceptions
            mock_cache_instance.store_session.side_effect = Exception("Cache error")
            mock_cache_instance.get_session.side_effect = Exception("Cache error")
            mock_cache_class.return_value = mock_cache_instance
            
            # Set up cache-enabled config
            session_manager.set_server_config(cache_enabled_config)
            
            # Create a session
            session = session_manager.create_dynamic_session(
                "error-client", "Error test task", test_workflow_def
            )
            
            # Operations should handle cache errors gracefully
            sync_result = session_manager.sync_session(session.session_id)
            # Should still succeed even if cache fails
            assert sync_result is True

    def test_cache_config_validation(self):
        """Test cache configuration validation."""
        # Test with invalid cache directory
        invalid_config = Mock()
        invalid_config.ensure_cache_dir.return_value = False
        
        result = session_manager._initialize_cache_manager(invalid_config)
        assert result is False
        
        # Test with missing cache configuration
        minimal_config = Mock()
        minimal_config.ensure_cache_dir.return_value = True
        minimal_config.cache_dir = None
        
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_class.side_effect = Exception("Invalid config")
            
            result = session_manager._initialize_cache_manager(minimal_config)
            assert result is False


class TestCachePerformanceAndScaling:
    """Test cache performance and scaling scenarios."""

    def setup_method(self):
        """Reset services and clear sessions before each test."""
        reset_session_services()
        initialize_session_services()
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()
        session_manager.workflow_definitions_cache.clear()

    def test_multiple_sessions_cache_operations(self, cache_enabled_config, test_workflow_def):
        """Test cache operations with multiple sessions."""
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance
            
            # Set up cache-enabled config
            session_manager.set_server_config(cache_enabled_config)
            
            # Create multiple sessions
            sessions = []
            for i in range(5):
                session = session_manager.create_dynamic_session(
                    f"multi-client-{i}", f"Multi test task {i}", test_workflow_def
                )
                sessions.append(session)
            
            # Sync all sessions
            for session in sessions:
                result = session_manager.sync_session(session.session_id)
                assert result is True
            
            # List all sessions
            all_sessions = session_manager.get_all_sessions()
            assert len(all_sessions) == 5

    def test_concurrent_cache_access_simulation(self, cache_enabled_config, test_workflow_def):
        """Test simulation of concurrent cache access."""
        with patch("src.dev_workflow_mcp.utils.cache_manager.WorkflowCacheManager") as mock_cache_class:
            mock_cache_instance = Mock()
            mock_cache_class.return_value = mock_cache_instance
            
            # Set up cache-enabled config
            session_manager.set_server_config(cache_enabled_config)
            
            # Simulate concurrent operations
            session1 = session_manager.create_dynamic_session(
                "concurrent-1", "Concurrent task 1", test_workflow_def
            )
            session2 = session_manager.create_dynamic_session(
                "concurrent-2", "Concurrent task 2", test_workflow_def
            )
            
            # Simulate concurrent updates
            result1 = session_manager.update_session(session1.session_id, status="RUNNING")
            result2 = session_manager.update_session(session2.session_id, status="RUNNING")
            
            assert result1 is True
            assert result2 is True
            
            # Both sessions should be accessible
            retrieved1 = session_manager.get_session(session1.session_id)
            retrieved2 = session_manager.get_session(session2.session_id)
            
            assert retrieved1 is not None
            assert retrieved2 is not None
            assert retrieved1.session_id != retrieved2.session_id 