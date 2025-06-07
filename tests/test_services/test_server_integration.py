"""Integration tests for server configuration migration."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from src.dev_workflow_mcp.services.config_service import (
    ConfigurationService,
    get_configuration_service,
    reset_configuration_service,
)
from src.dev_workflow_mcp.services.dependency_injection import (
    clear_registry,
    get_service,
)


class TestServerConfigurationIntegration:
    """Test server configuration integration with new configuration service."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_configuration_service()
        clear_registry()

    def teardown_method(self):
        """Clean up after tests."""
        reset_configuration_service()
        clear_registry()

    def test_server_configuration_creation_from_cli_args(self):
        """Test server configuration creation from command-line arguments."""
        from src.dev_workflow_mcp.server import create_arg_parser

        parser = create_arg_parser()

        # Test with default arguments
        args = parser.parse_args([])

        assert args.repository_path is None
        assert args.enable_local_state_file is False
        assert args.local_state_file_format == "MD"
        assert args.session_retention_hours == 168
        assert args.disable_session_archiving is False
        assert args.enable_cache_mode is False
        assert args.cache_db_path is None
        assert args.cache_collection_name == "workflow_states"
        assert args.cache_embedding_model == "all-MiniLM-L6-v2"
        assert args.cache_max_results == 50

    def test_server_configuration_creation_with_custom_args(self):
        """Test server configuration creation with custom command-line arguments."""
        from src.dev_workflow_mcp.server import create_arg_parser

        parser = create_arg_parser()

        with tempfile.TemporaryDirectory() as temp_dir:
            args = parser.parse_args(
                [
                    "--repository-path",
                    temp_dir,
                    "--enable-local-state-file",
                    "--local-state-file-format",
                    "JSON",
                    "--session-retention-hours",
                    "24",
                    "--disable-session-archiving",
                    "--enable-cache-mode",
                    "--cache-db-path",
                    "/custom/cache",
                    "--cache-collection-name",
                    "custom_collection",
                    "--cache-embedding-model",
                    "custom-model",
                    "--cache-max-results",
                    "100",
                ]
            )

            assert args.repository_path == temp_dir
            assert args.enable_local_state_file is True
            assert args.local_state_file_format == "JSON"
            assert args.session_retention_hours == 24
            assert args.disable_session_archiving is True
            assert args.enable_cache_mode is True
            assert args.cache_db_path == "/custom/cache"
            assert args.cache_collection_name == "custom_collection"
            assert args.cache_embedding_model == "custom-model"
            assert args.cache_max_results == 100

    @patch("src.dev_workflow_mcp.server.FastMCP")
    @patch("src.dev_workflow_mcp.server.register_phase_prompts")
    @patch("src.dev_workflow_mcp.server.register_discovery_prompts")
    def test_server_startup_with_configuration_service(
        self, mock_register_discovery, mock_register_phase, mock_fastmcp
    ):
        """Test server startup with new configuration service."""
        from src.dev_workflow_mcp.server import main

        # Mock FastMCP instance
        mock_mcp_instance = Mock()
        mock_fastmcp.return_value = mock_mcp_instance

        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock sys.argv to simulate command-line arguments
            test_args = [
                "server.py",
                "--repository-path",
                temp_dir,
                "--enable-local-state-file",
                "--local-state-file-format",
                "JSON",
            ]

            with patch("sys.argv", test_args):
                result = main()

                # Verify successful startup
                assert result == 0

                # Verify FastMCP was initialized
                mock_fastmcp.assert_called_once_with("Development Workflow")

                # Verify prompts were registered
                mock_register_phase.assert_called_once()
                mock_register_discovery.assert_called_once()

                # Verify server was started
                mock_mcp_instance.run.assert_called_once_with(transport="stdio")

                # Verify configuration service was initialized
                config_service = get_configuration_service()
                assert isinstance(config_service, ConfigurationService)

                # Verify configuration values
                server_config = config_service.get_server_config()
                assert server_config.repository_path == Path(temp_dir)
                assert server_config.enable_local_state_file is True
                assert server_config.local_state_file_format == "JSON"

                workflow_config = config_service.get_workflow_config()
                assert workflow_config.local_state_file is True
                assert workflow_config.local_state_file_format == "JSON"

    @patch("src.dev_workflow_mcp.server.FastMCP")
    @patch("src.dev_workflow_mcp.server.register_phase_prompts")
    @patch("src.dev_workflow_mcp.server.register_discovery_prompts")
    def test_server_startup_with_cache_mode(
        self, mock_register_discovery, mock_register_phase, mock_fastmcp
    ):
        """Test server startup with cache mode enabled."""
        from src.dev_workflow_mcp.server import main

        # Mock FastMCP instance
        mock_mcp_instance = Mock()
        mock_fastmcp.return_value = mock_mcp_instance

        with tempfile.TemporaryDirectory() as temp_dir:
            test_args = [
                "server.py",
                "--repository-path",
                temp_dir,
                "--enable-cache-mode",
                "--cache-max-results",
                "75",
            ]

            with patch("sys.argv", test_args):
                with patch(
                    "src.dev_workflow_mcp.utils.session_manager.auto_restore_sessions_on_startup"
                ) as mock_restore:
                    mock_restore.return_value = 2  # Simulate 2 restored sessions

                    result = main()

                    # Verify successful startup
                    assert result == 0

                    # Verify cache restoration was attempted
                    mock_restore.assert_called_once()

                    # Verify configuration service has cache mode enabled
                    config_service = get_configuration_service()
                    server_config = config_service.get_server_config()
                    assert server_config.enable_cache_mode is True
                    assert server_config.cache_max_results == 75

    @patch("src.dev_workflow_mcp.server.FastMCP")
    def test_server_startup_configuration_error(self, mock_fastmcp):
        """Test server startup with configuration error."""
        from src.dev_workflow_mcp.server import main

        # Test with invalid repository path
        test_args = [
            "server.py",
            "--repository-path",
            "/nonexistent/path/that/does/not/exist",
        ]

        with patch("sys.argv", test_args):
            result = main()

            # Verify error exit code
            assert result == 1

            # Verify FastMCP was not initialized
            mock_fastmcp.assert_not_called()

    def test_dependency_injection_registration(self):
        """Test that configuration service is properly registered in dependency injection."""
        from src.dev_workflow_mcp.server import main

        with tempfile.TemporaryDirectory() as temp_dir:
            test_args = [
                "server.py",
                "--repository-path",
                temp_dir,
            ]

            with patch("sys.argv", test_args):
                with patch("src.dev_workflow_mcp.server.FastMCP"):
                    with patch("src.dev_workflow_mcp.server.register_phase_prompts"):
                        with patch(
                            "src.dev_workflow_mcp.server.register_discovery_prompts"
                        ):
                            result = main()

                            assert result == 0

                            # Verify configuration service is available via dependency injection
                            config_service = get_service(ConfigurationService)
                            assert isinstance(config_service, ConfigurationService)

                            # Verify it's the same instance as the global service
                            global_service = get_configuration_service()
                            assert config_service is global_service

    def test_backward_compatibility_legacy_config(self):
        """Test that legacy ServerConfig is still created for backward compatibility."""
        from src.dev_workflow_mcp.config import ServerConfig
        from src.dev_workflow_mcp.server import main

        with tempfile.TemporaryDirectory() as temp_dir:
            test_args = [
                "server.py",
                "--repository-path",
                temp_dir,
                "--enable-local-state-file",
            ]

            with patch("sys.argv", test_args):
                with patch("src.dev_workflow_mcp.server.FastMCP"):
                    with patch(
                        "src.dev_workflow_mcp.server.register_phase_prompts"
                    ) as mock_register_phase:
                        with patch(
                            "src.dev_workflow_mcp.server.register_discovery_prompts"
                        ) as mock_register_discovery:
                            result = main()

                            assert result == 0

                            # Verify legacy config was passed to prompt registration
                            mock_register_phase.assert_called_once()
                            mock_register_discovery.assert_called_once()

                            # Get the config that was passed to the registration functions
                            phase_config = mock_register_phase.call_args[0][1]
                            discovery_config = mock_register_discovery.call_args[0][1]

                            # Verify it's a legacy ServerConfig instance
                            assert isinstance(phase_config, ServerConfig)
                            assert isinstance(discovery_config, ServerConfig)

                            # Verify configuration values match
                            assert str(phase_config.repository_path) == temp_dir
                            assert phase_config.enable_local_state_file is True
