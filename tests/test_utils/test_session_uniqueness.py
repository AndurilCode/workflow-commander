"""Tests for session file uniqueness and archiving functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from src.dev_workflow_mcp.config import ServerConfig
from src.dev_workflow_mcp.services.config_service import (
    ServerConfiguration,
    initialize_configuration_service,
    reset_configuration_service,
)
from src.dev_workflow_mcp.utils import session_manager
from src.dev_workflow_mcp.utils.session_manager import (
    _archive_session_file,
    _generate_unique_session_filename,
    cleanup_completed_sessions,
    set_server_config,
)


class TestSessionFilenameGeneration:
    """Test unique session filename generation."""

    def setup_method(self):
        """Clear all sessions before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()

    def test_generate_unique_session_filename_basic(self):
        """Test basic unique filename generation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            sessions_dir = Path(temp_dir)

            filename = _generate_unique_session_filename(
                "test_client", "json", sessions_dir
            )

            # Should match pattern: client_timestamp_counter.ext
            assert filename.startswith("test_client_")
            assert filename.endswith("_001.json")
            assert len(filename.split("_")) >= 4  # client, date, time, counter

    def test_generate_unique_session_filename_collision_handling(self):
        """Test filename generation handles collisions with incremented counter."""
        with tempfile.TemporaryDirectory() as temp_dir:
            sessions_dir = Path(temp_dir)

            # Mock datetime to ensure same timestamp
            with patch(
                "src.dev_workflow_mcp.utils.session_manager.datetime"
            ) as mock_dt:
                mock_dt.now.return_value.strftime.return_value = "2025-06-04T10-30-00"

                # Generate first filename
                filename1 = _generate_unique_session_filename(
                    "test", "json", sessions_dir
                )

                # Create the file to simulate collision
                (sessions_dir / filename1).write_text("{}")

                # Generate second filename - should increment counter
                filename2 = _generate_unique_session_filename(
                    "test", "json", sessions_dir
                )

                assert filename1 == "test_2025-06-04T10-30-00_001.json"
                assert filename2 == "test_2025-06-04T10-30-00_002.json"

    def test_generate_unique_session_filename_client_id_sanitization(self):
        """Test client ID sanitization for filesystem safety."""
        with tempfile.TemporaryDirectory() as temp_dir:
            sessions_dir = Path(temp_dir)

            # Test various problematic characters
            unsafe_client_id = "user@domain.com/test:client"
            filename = _generate_unique_session_filename(
                unsafe_client_id, "md", sessions_dir
            )

            # Should replace unsafe characters with underscores
            assert filename.startswith("user_domain_com_test_client_")
            assert filename.endswith("_001.md")

    def test_generate_unique_session_filename_different_extensions(self):
        """Test filename generation with different extensions."""
        with tempfile.TemporaryDirectory() as temp_dir:
            sessions_dir = Path(temp_dir)

            json_filename = _generate_unique_session_filename(
                "client", "json", sessions_dir
            )
            md_filename = _generate_unique_session_filename(
                "client", "md", sessions_dir
            )

            assert json_filename.endswith(".json")
            assert md_filename.endswith(".md")


class TestSessionArchiving:
    """Test session archiving functionality."""

    def setup_method(self):
        """Clear all sessions before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()

    def test_archive_session_file_basic(self):
        """Test basic session file archiving functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test config using new configuration service
            server_config = ServerConfiguration(
                repository_path=Path(temp_dir),
                enable_local_state_file=True,
                local_state_file_format="JSON",
            )

            # Initialize configuration service
            config_service = initialize_configuration_service(
                server_config=server_config
            )

            # Ensure sessions directory exists
            server_config.sessions_dir.mkdir(parents=True, exist_ok=True)

            # Create test session with file
            from src.dev_workflow_mcp.models.workflow_state import DynamicWorkflowState

            session = DynamicWorkflowState(
                client_id="test_client",
                workflow_name="Test Workflow",
                current_node="start",
                status="COMPLETED",
                session_filename="test_client_2025-06-04T10-30-00_001.json",
            )

            # Create the actual file
            session_file = server_config.sessions_dir / session.session_filename
            session_file.write_text('{"test": "data"}')

            # Archive the session
            result = _archive_session_file(session)

            assert result is True
            assert not session_file.exists()  # Original file should be moved

            # Check archived file exists
            archived_files = list(server_config.sessions_dir.glob("*_COMPLETED_*.json"))
            assert len(archived_files) == 1
            assert (
                "test_client_2025-06-04T10-30-00_001_COMPLETED_"
                in archived_files[0].name
            )

    def test_archive_session_file_no_config(self):
        """Test archiving with no server config - should skip gracefully."""
        from src.dev_workflow_mcp.models.workflow_state import DynamicWorkflowState

        session = DynamicWorkflowState(
            client_id="test_client",
            workflow_name="Test Workflow",
            current_node="start",
            status="COMPLETED",
            session_filename="test.json",
        )

        # Clear configuration service
        reset_configuration_service()

        result = _archive_session_file(session)
        assert result is True  # Should succeed but skip archiving

    def test_archive_session_file_no_filename(self):
        """Test archiving session without filename - should skip gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ServerConfig(
                repository_path=temp_dir, enable_local_state_file=True
            )
            set_server_config(config)

            from src.dev_workflow_mcp.models.workflow_state import DynamicWorkflowState

            session = DynamicWorkflowState(
                client_id="test_client",
                workflow_name="Test Workflow",
                current_node="start",
                status="COMPLETED",
                session_filename=None,  # No filename
            )

            result = _archive_session_file(session)
            assert result is True  # Should succeed but skip archiving


class TestCleanupWithArchiving:
    """Test cleanup functionality with archiving."""

    def setup_method(self):
        """Clear all sessions before each test."""
        # Reset services to ensure clean state
        from src.dev_workflow_mcp.services import reset_session_services, initialize_session_services
        reset_session_services()
        initialize_session_services()
        
        session_manager.sessions.clear()
        session_manager.client_session_registry.clear()

    def test_cleanup_completed_sessions_with_archiving(self):
        """Test cleanup archives sessions before removing them from memory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test config using new configuration service
            server_config = ServerConfiguration(
                repository_path=Path(temp_dir),
                enable_local_state_file=True,
                local_state_file_format="JSON",
            )

            # Initialize configuration service
            config_service = initialize_configuration_service(
                server_config=server_config
            )

            # Ensure sessions directory exists
            server_config.sessions_dir.mkdir(parents=True, exist_ok=True)

            # Create completed session
            from datetime import UTC, datetime, timedelta

            from src.dev_workflow_mcp.models.workflow_state import DynamicWorkflowState

            old_time = datetime.now(UTC) - timedelta(hours=48)  # 48 hours ago

            session = DynamicWorkflowState(
                client_id="old_client",
                workflow_name="Test Workflow",
                current_node="end",
                status="COMPLETED",
                session_filename="old_client_session.json",
                created_at=old_time,
                last_updated=old_time,
            )

            # Add to sessions
            session_manager.sessions[session.session_id] = session

            # Create the actual file
            session_file = server_config.sessions_dir / session.session_filename
            session_file.write_text('{"test": "completed_data"}')

            # Run cleanup with archiving enabled
            cleaned_count = cleanup_completed_sessions(
                keep_recent_hours=24, archive_before_cleanup=True
            )

            assert cleaned_count == 1
            assert session.session_id not in session_manager.sessions

            # Check that file was archived
            archived_files = list(server_config.sessions_dir.glob("*_COMPLETED_*.json"))
            assert len(archived_files) == 1

    def test_cleanup_completed_sessions_without_archiving(self):
        """Test cleanup without archiving."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = ServerConfig(
                repository_path=temp_dir,
                enable_local_state_file=True,
                local_state_file_format="JSON",
            )
            set_server_config(config)
            config.ensure_sessions_dir()

            from datetime import UTC, datetime, timedelta

            from src.dev_workflow_mcp.models.workflow_state import DynamicWorkflowState

            old_time = datetime.now(UTC) - timedelta(hours=48)

            session = DynamicWorkflowState(
                client_id="old_client",
                workflow_name="Test Workflow",
                current_node="end",
                status="COMPLETED",
                session_filename="old_client_session.json",
                created_at=old_time,
                last_updated=old_time,
            )

            session_manager.sessions[session.session_id] = session

            # Create the actual file
            session_file = config.sessions_dir / session.session_filename
            session_file.write_text('{"test": "completed_data"}')

            # Run cleanup without archiving
            cleaned_count = cleanup_completed_sessions(
                keep_recent_hours=24, archive_before_cleanup=False
            )

            assert cleaned_count == 1
            assert session.session_id not in session_manager.sessions

            # Check that no archived files were created
            archived_files = list(config.sessions_dir.glob("*_COMPLETED_*.json"))
            assert len(archived_files) == 0


class TestServerConfigExtensions:
    """Test new ServerConfig session management options."""

    def test_server_config_session_management_defaults(self):
        """Test default values for session management configuration."""
        config = ServerConfig()

        assert config.session_retention_hours == 168  # 7 days
        assert config.enable_session_archiving is True

    def test_server_config_session_management_custom(self):
        """Test custom values for session management configuration."""
        config = ServerConfig(
            session_retention_hours=72,  # 3 days
            enable_session_archiving=False,
        )

        assert config.session_retention_hours == 72
        assert config.enable_session_archiving is False

    def test_server_config_session_retention_minimum(self):
        """Test minimum retention hours enforcement."""
        config = ServerConfig(session_retention_hours=0)  # Invalid: too low

        assert config.session_retention_hours == 1  # Should be enforced to minimum
