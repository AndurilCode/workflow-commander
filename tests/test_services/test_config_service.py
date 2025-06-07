"""Tests for configuration service."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.dev_workflow_mcp.services.config_service import (
    ConfigurationError,
    ConfigurationService,
    ConfigurationValidationError,
    EnvironmentConfiguration,
    PlatformConfiguration,
    PlatformType,
    ServerConfiguration,
    WorkflowConfiguration,
    get_configuration_service,
    initialize_configuration_service,
    reset_configuration_service,
)


class TestServerConfiguration:
    """Test ServerConfiguration model."""

    def test_default_configuration(self):
        """Test default server configuration."""
        config = ServerConfiguration()

        assert config.repository_path == Path.cwd()
        assert config.enable_local_state_file is False
        assert config.local_state_file_format == "MD"
        assert config.session_retention_hours == 168
        assert config.enable_session_archiving is True
        assert config.enable_cache_mode is False
        assert config.cache_db_path is None
        assert config.cache_collection_name == "workflow_states"
        assert config.cache_embedding_model == "all-MiniLM-L6-v2"
        assert config.cache_max_results == 50

    def test_custom_configuration(self):
        """Test server configuration with custom values."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)

            config = ServerConfiguration(
                repository_path=repo_path,
                enable_local_state_file=True,
                local_state_file_format="JSON",
                session_retention_hours=24,
                enable_session_archiving=False,
                enable_cache_mode=True,
                cache_db_path="/custom/cache",
                cache_collection_name="custom_collection",
                cache_embedding_model="custom-model",
                cache_max_results=100,
            )

            assert config.repository_path == repo_path
            assert config.enable_local_state_file is True
            assert config.local_state_file_format == "JSON"
            assert config.session_retention_hours == 24
            assert config.enable_session_archiving is False
            assert config.enable_cache_mode is True
            assert config.cache_db_path == "/custom/cache"
            assert config.cache_collection_name == "custom_collection"
            assert config.cache_embedding_model == "custom-model"
            assert config.cache_max_results == 100

    def test_path_properties(self):
        """Test computed path properties."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)
            config = ServerConfiguration(repository_path=repo_path)

            expected_workflow_dir = repo_path / ".workflow-commander"
            expected_workflows_dir = expected_workflow_dir / "workflows"
            expected_sessions_dir = expected_workflow_dir / "sessions"
            expected_project_config = expected_workflow_dir / "project_config.md"
            expected_cache_dir = expected_workflow_dir / "cache"

            assert config.workflow_commander_dir == expected_workflow_dir
            assert config.workflows_dir == expected_workflows_dir
            assert config.sessions_dir == expected_sessions_dir
            assert config.project_config_path == expected_project_config
            assert config.cache_dir == expected_cache_dir

    def test_custom_cache_dir(self):
        """Test cache directory with custom path."""
        config = ServerConfiguration(cache_db_path="/custom/cache/path")
        assert config.cache_dir == Path("/custom/cache/path")


class TestWorkflowConfiguration:
    """Test WorkflowConfiguration model."""

    def test_default_configuration(self):
        """Test default workflow configuration."""
        config = WorkflowConfiguration()

        assert config.local_state_file is False
        assert config.local_state_file_format == "MD"
        assert config.default_max_depth == 10
        assert config.allow_backtracking is True

    def test_custom_configuration(self):
        """Test workflow configuration with custom values."""
        config = WorkflowConfiguration(
            local_state_file=True,
            local_state_file_format="JSON",
            default_max_depth=20,
            allow_backtracking=False,
        )

        assert config.local_state_file is True
        assert config.local_state_file_format == "JSON"
        assert config.default_max_depth == 20
        assert config.allow_backtracking is False


class TestPlatformConfiguration:
    """Test PlatformConfiguration model."""

    def test_default_configuration(self):
        """Test default platform configuration."""
        config = PlatformConfiguration()

        # Test defaults
        assert config.editor_type == PlatformType.CURSOR
        assert config.cli_enabled is True
        assert config.environment_variables == {}

        # Test auto-population of platform info
        assert config.platform_info is not None
        assert config.platform_info.name == "Cursor"
        assert config.platform_info.platform_type == PlatformType.CURSOR

        # Test auto-configuration of handler
        assert config.handler_config is not None
        assert config.handler_config.handler_class == "CursorHandler"
        assert (
            config.handler_config.module_path
            == "workflow_commander_cli.handlers.cursor"
        )

        # Test default settings
        assert config.config_file_management["auto_backup"] is True
        assert config.cli_integration["enable_auto_detection"] is True
        assert config.transport_settings["preferred_transport"] == "stdio"

    def test_custom_configuration(self):
        """Test platform configuration with custom values."""
        config = PlatformConfiguration(
            editor_type=PlatformType.VSCODE,
            cli_enabled=False,
            environment_variables={"TEST_VAR": "test_value"},
        )

        # Test custom values
        assert config.editor_type == PlatformType.VSCODE
        assert config.cli_enabled is False
        assert config.environment_variables == {"TEST_VAR": "test_value"}

        # Test auto-population for VS Code
        assert config.platform_info is not None
        assert config.platform_info.name == "VS Code"
        assert config.platform_info.platform_type == PlatformType.VSCODE
        assert config.platform_info.config_format == "mcp.servers"

        # Test VS Code handler auto-configuration
        assert config.handler_config is not None
        assert config.handler_config.handler_class == "VSCodeHandler"
        assert (
            config.handler_config.module_path
            == "workflow_commander_cli.handlers.vscode"
        )

    def test_platform_info_auto_detection(self):
        """Test platform info auto-detection for all platform types."""
        platforms = [
            (PlatformType.CURSOR, "Cursor", "mcpServers"),
            (PlatformType.CLAUDE_DESKTOP, "Claude Desktop", "mcpServers"),
            (PlatformType.CLAUDE_CODE, "Claude Code", "mcpServers"),
            (PlatformType.VSCODE, "VS Code", "mcp.servers"),
        ]

        for platform_type, expected_name, expected_format in platforms:
            config = PlatformConfiguration(editor_type=platform_type)

            assert config.platform_info is not None
            assert config.platform_info.name == expected_name
            assert config.platform_info.platform_type == platform_type
            assert config.platform_info.config_format == expected_format
            assert config.platform_info.locations is not None
            assert len(config.platform_info.supported_transports) > 0

    def test_config_location_methods(self):
        """Test configuration location resolution methods."""
        from pathlib import Path

        config = PlatformConfiguration(editor_type=PlatformType.CURSOR)

        # Test global location
        global_path = config.get_config_location(use_global=True)
        assert global_path is not None
        assert isinstance(global_path, Path)

        # Test project location
        project_root = Path("/tmp/test-project")
        project_path = config.get_config_location(
            use_global=False, project_root=project_root
        )
        assert project_path is not None
        assert isinstance(project_path, Path)

        # Test supported transports
        transports = config.get_supported_transports()
        assert isinstance(transports, list)
        assert len(transports) > 0
        assert "stdio" in transports

    def test_platform_validation(self):
        """Test platform compatibility validation."""
        config = PlatformConfiguration(editor_type=PlatformType.CURSOR)

        # Test validation
        is_valid, issues = config.validate_platform_compatibility()

        # Validation may fail depending on system setup, but should return proper format
        assert isinstance(is_valid, bool)
        assert isinstance(issues, list)

        # All issues should be strings
        for issue in issues:
            assert isinstance(issue, str)

    def test_handler_configuration_mapping(self):
        """Test handler configuration mapping for all platforms."""
        handler_expectations = {
            PlatformType.CURSOR: (
                "CursorHandler",
                "workflow_commander_cli.handlers.cursor",
            ),
            PlatformType.CLAUDE_DESKTOP: (
                "ClaudeDesktopHandler",
                "workflow_commander_cli.handlers.claude",
            ),
            PlatformType.CLAUDE_CODE: (
                "ClaudeCodeHandler",
                "workflow_commander_cli.handlers.claude",
            ),
            PlatformType.VSCODE: (
                "VSCodeHandler",
                "workflow_commander_cli.handlers.vscode",
            ),
        }

        for platform_type, (
            expected_class,
            expected_module,
        ) in handler_expectations.items():
            config = PlatformConfiguration(editor_type=platform_type)

            assert config.handler_config is not None
            assert config.handler_config.handler_class == expected_class
            assert config.handler_config.module_path == expected_module
            assert config.handler_config.config_validation is True
            assert config.handler_config.backup_configs is True

    def test_transport_settings_validation(self):
        """Test transport settings validation."""
        # Test with invalid preferred transport
        config = PlatformConfiguration(
            editor_type=PlatformType.CURSOR,
            transport_settings={
                "preferred_transport": "invalid_transport",
                "fallback_transports": ["stdio", "sse"],
                "timeout_seconds": 30,
            },
        )

        is_valid, issues = config.validate_platform_compatibility()

        # Should detect invalid transport
        transport_issue = any("transport" in issue.lower() for issue in issues)
        if not is_valid:
            assert transport_issue

    def test_environment_variable_integration(self):
        """Test environment variable integration."""
        test_env = {"EDITOR": "cursor", "PLATFORM_CONFIG": "test", "DEBUG": "true"}

        config = PlatformConfiguration(
            editor_type=PlatformType.CURSOR, environment_variables=test_env
        )

        assert config.environment_variables == test_env

    def test_cli_integration_settings(self):
        """Test CLI integration configuration."""
        config = PlatformConfiguration()

        # Test default CLI integration settings
        cli_settings = config.cli_integration
        assert cli_settings["enable_auto_detection"] is True
        assert cli_settings["preferred_config_location"] == "global"
        assert "configure" in cli_settings["supported_commands"]
        assert "list-servers" in cli_settings["supported_commands"]
        assert "remove-server" in cli_settings["supported_commands"]
        assert "validate" in cli_settings["supported_commands"]
        assert cli_settings["non_interactive_defaults"] is True

    def test_config_file_management_settings(self):
        """Test configuration file management settings."""
        config = PlatformConfiguration()

        # Test default file management settings
        file_mgmt = config.config_file_management
        assert file_mgmt["auto_backup"] is True
        assert file_mgmt["backup_retention_days"] == 7
        assert file_mgmt["merge_strategy"] == "preserve_existing"
        assert file_mgmt["validate_on_save"] is True

    def test_invalid_platform_info_handling(self):
        """Test handling when platform info is unavailable."""
        # Create config and then manually set platform_info to None
        config = PlatformConfiguration(editor_type=PlatformType.CURSOR)

        # Manually override the platform info to simulate missing info
        config.platform_info = None

        # Test validation with missing platform info
        is_valid, issues = config.validate_platform_compatibility()
        assert not is_valid
        assert any(
            "platform information not available" in issue.lower() for issue in issues
        )

        # Test methods that require platform info
        try:
            config.get_config_location()
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "platform info not configured" in str(e).lower()

        # Test fallback for supported transports
        transports = config.get_supported_transports()
        assert transports == ["stdio"]  # Default fallback from transport_settings


class TestEnvironmentConfiguration:
    """Test EnvironmentConfiguration model."""

    def test_default_configuration_no_env_vars(self):
        """Test default environment configuration without environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            config = EnvironmentConfiguration()

            assert config.s3_enabled is False
            assert config.s3_bucket_name is None
            assert config.s3_prefix == "workflow-states/"
            assert config.s3_region == "us-east-1"
            assert config.s3_sync_on_finalize is True
            assert config.s3_archive_completed is True

    def test_configuration_with_env_vars(self):
        """Test environment configuration with environment variables set."""
        env_vars = {
            "S3_BUCKET_NAME": "test-bucket",
            "S3_PREFIX": "custom-prefix/",
            "AWS_REGION": "us-west-2",
            "S3_SYNC_ON_FINALIZE": "false",
            "S3_ARCHIVE_COMPLETED": "false",
        }

        with patch.dict(os.environ, env_vars):
            config = EnvironmentConfiguration()

            assert config.s3_enabled is True
            assert config.s3_bucket_name == "test-bucket"
            assert config.s3_prefix == "custom-prefix/"
            assert config.s3_region == "us-west-2"
            assert config.s3_sync_on_finalize is False
            assert config.s3_archive_completed is False

    def test_s3_enabled_auto_detection(self):
        """Test S3 enabled auto-detection based on bucket name."""
        with patch.dict(os.environ, {"S3_BUCKET_NAME": "test-bucket"}):
            config = EnvironmentConfiguration()
            assert config.s3_enabled is True

        with patch.dict(os.environ, {}, clear=True):
            config = EnvironmentConfiguration()
            assert config.s3_enabled is False


class TestConfigurationService:
    """Test ConfigurationService implementation."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_configuration_service()

    def teardown_method(self):
        """Clean up after tests."""
        reset_configuration_service()

    def test_initialization_with_defaults(self):
        """Test configuration service initialization with default values."""
        service = ConfigurationService()

        assert isinstance(service.get_server_config(), ServerConfiguration)
        assert isinstance(service.get_workflow_config(), WorkflowConfiguration)
        assert isinstance(service.get_platform_config(), PlatformConfiguration)
        assert isinstance(service.get_environment_config(), EnvironmentConfiguration)

    def test_initialization_with_custom_configs(self):
        """Test configuration service initialization with custom configuration objects."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server_config = ServerConfiguration(
                repository_path=Path(temp_dir),
                enable_cache_mode=True,
            )
            workflow_config = WorkflowConfiguration(local_state_file=True)
            platform_config = PlatformConfiguration(editor_type="vscode")

            with patch.dict(os.environ, {"S3_BUCKET_NAME": "test-bucket"}):
                environment_config = EnvironmentConfiguration()

            service = ConfigurationService(
                server_config=server_config,
                workflow_config=workflow_config,
                platform_config=platform_config,
                environment_config=environment_config,
            )

            assert service.get_server_config() == server_config
            assert service.get_workflow_config() == workflow_config
            assert service.get_platform_config() == platform_config
            assert service.get_environment_config() == environment_config

    def test_validation_success(self):
        """Test configuration validation with valid configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server_config = ServerConfiguration(repository_path=Path(temp_dir))
            service = ConfigurationService(server_config=server_config)

            is_valid, issues = service.validate_configuration()
            assert is_valid is True
            assert issues == []

    def test_validation_failure_invalid_repository_path(self):
        """Test configuration validation with invalid repository path."""
        server_config = ServerConfiguration(repository_path=Path("/nonexistent/path"))

        with pytest.raises(ConfigurationValidationError):
            ConfigurationService(server_config=server_config)

    def test_validation_failure_s3_config(self):
        """Test configuration validation with invalid S3 configuration."""
        with patch.dict(os.environ, {"S3_BUCKET_NAME": ""}):
            # This should create an environment config where s3_enabled=False due to empty bucket name
            service = ConfigurationService()
            is_valid, issues = service.validate_configuration()
            assert is_valid is True  # Should be valid because S3 auto-disables

    def test_reload_configuration(self):
        """Test configuration reload functionality."""
        service = ConfigurationService()

        # Initial state
        assert service.get_environment_config().s3_enabled is False

        # Mock environment change and reload
        with patch.dict(os.environ, {"S3_BUCKET_NAME": "new-bucket"}):
            success = service.reload_configuration()
            assert success is True
            assert service.get_environment_config().s3_enabled is True
            assert service.get_environment_config().s3_bucket_name == "new-bucket"

    def test_update_server_config(self):
        """Test server configuration update functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ConfigurationService()

            # Update server configuration
            service.update_server_config(
                repository_path=Path(temp_dir),
                enable_cache_mode=True,
                cache_max_results=100,
            )

            server_config = service.get_server_config()
            assert server_config.repository_path == Path(temp_dir)
            assert server_config.enable_cache_mode is True
            assert server_config.cache_max_results == 100

    def test_update_server_config_validation_failure(self):
        """Test server configuration update with validation failure."""
        service = ConfigurationService()

        with pytest.raises(ConfigurationValidationError):
            service.update_server_config(repository_path=Path("/nonexistent/path"))

    def test_to_legacy_server_config(self):
        """Test conversion to legacy ServerConfig."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server_config = ServerConfiguration(
                repository_path=Path(temp_dir),
                enable_local_state_file=True,
                local_state_file_format="JSON",
                enable_cache_mode=True,
            )

            service = ConfigurationService(server_config=server_config)
            legacy_config = service.to_legacy_server_config()

            # Import here to avoid circular imports
            from src.dev_workflow_mcp.config import ServerConfig

            assert isinstance(legacy_config, ServerConfig)
            assert str(legacy_config.repository_path) == str(temp_dir)
            assert legacy_config.enable_local_state_file is True
            assert legacy_config.local_state_file_format == "JSON"
            assert legacy_config.enable_cache_mode is True


class TestConfigurationServiceGlobalFunctions:
    """Test global configuration service functions."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_configuration_service()

    def teardown_method(self):
        """Clean up after tests."""
        reset_configuration_service()

    def test_initialize_and_get_configuration_service(self):
        """Test global configuration service initialization and retrieval."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server_config = ServerConfiguration(repository_path=Path(temp_dir))

            # Initialize service
            service = initialize_configuration_service(server_config=server_config)
            assert isinstance(service, ConfigurationService)

            # Retrieve service
            retrieved_service = get_configuration_service()
            assert retrieved_service is service
            assert retrieved_service.get_server_config() == server_config

    def test_get_configuration_service_not_initialized(self):
        """Test getting configuration service when not initialized."""
        with pytest.raises(
            ConfigurationError, match="Configuration service not initialized"
        ):
            get_configuration_service()

    def test_reset_configuration_service(self):
        """Test resetting configuration service."""
        with tempfile.TemporaryDirectory() as temp_dir:
            server_config = ServerConfiguration(repository_path=Path(temp_dir))
            initialize_configuration_service(server_config=server_config)

            # Service should be available
            service = get_configuration_service()
            assert isinstance(service, ConfigurationService)

            # Reset service
            reset_configuration_service()

            # Service should no longer be available
            with pytest.raises(ConfigurationError):
                get_configuration_service()


class TestConfigurationServiceProtocol:
    """Test that ConfigurationService implements the protocol correctly."""

    def test_protocol_implementation(self):
        """Test that ConfigurationService implements ConfigurationServiceProtocol."""
        service = ConfigurationService()

        # Test protocol methods exist and return correct types
        assert hasattr(service, "get_server_config")
        assert hasattr(service, "get_workflow_config")
        assert hasattr(service, "get_platform_config")
        assert hasattr(service, "get_environment_config")
        assert hasattr(service, "validate_configuration")
        assert hasattr(service, "reload_configuration")

        # Test protocol methods work correctly
        assert isinstance(service.get_server_config(), ServerConfiguration)
        assert isinstance(service.get_workflow_config(), WorkflowConfiguration)
        assert isinstance(service.get_platform_config(), PlatformConfiguration)
        assert isinstance(service.get_environment_config(), EnvironmentConfiguration)

        is_valid, issues = service.validate_configuration()
        assert isinstance(is_valid, bool)
        assert isinstance(issues, list)

        success = service.reload_configuration()
        assert isinstance(success, bool)
