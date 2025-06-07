"""Tests for the main server module."""

import sys
from unittest.mock import Mock, patch

import pytest

from src.dev_workflow_mcp.server import create_arg_parser, main


class TestArgumentParsing:
    """Test command-line argument parsing."""

    def test_create_arg_parser(self):
        """Test that argument parser is created correctly."""
        parser = create_arg_parser()

        # Test help message
        help_text = parser.format_help()
        assert "Development Workflow MCP Server" in help_text
        assert "--repository-path" in help_text

    def test_arg_parser_default_values(self):
        """Test argument parser with default values."""
        parser = create_arg_parser()
        args = parser.parse_args([])

        assert args.repository_path is None

    def test_arg_parser_with_repository_path(self):
        """Test argument parser with repository path specified."""
        parser = create_arg_parser()
        args = parser.parse_args(["--repository-path", "/some/path"])

        assert args.repository_path == "/some/path"


class TestMainFunction:
    """Test main function."""

    @patch("src.dev_workflow_mcp.server.FastMCP")
    @patch("src.dev_workflow_mcp.server.initialize_configuration_service")
    @patch("src.dev_workflow_mcp.server.register_phase_prompts")
    @patch("src.dev_workflow_mcp.server.register_discovery_prompts")
    def test_main_with_default_args(
        self,
        mock_register_discovery,
        mock_register_phase,
        mock_init_config,
        mock_fastmcp,
    ):
        """Test main function with default arguments."""
        # Mock FastMCP instance
        mock_mcp_instance = Mock()
        mock_fastmcp.return_value = mock_mcp_instance

        # Mock configuration service
        mock_config_service = Mock()
        mock_legacy_config = Mock()
        mock_config_service.to_legacy_server_config.return_value = mock_legacy_config
        mock_init_config.return_value = mock_config_service

        # Mock sys.argv to provide no arguments
        test_args = ["server.py"]
        with patch.object(sys, "argv", test_args):
            result = main()

        # Verify configuration service was initialized
        mock_init_config.assert_called_once()

        # Verify FastMCP was created
        mock_fastmcp.assert_called_once_with("Development Workflow")

        # Verify registration functions were called with legacy config
        mock_register_phase.assert_called_once_with(
            mock_mcp_instance, mock_legacy_config
        )
        mock_register_discovery.assert_called_once_with(
            mock_mcp_instance, mock_legacy_config
        )

        # Verify mcp.run was called
        mock_mcp_instance.run.assert_called_once_with(transport="stdio")

        # Verify successful return
        assert result == 0

    @patch("src.dev_workflow_mcp.server.FastMCP")
    @patch("src.dev_workflow_mcp.server.initialize_configuration_service")
    @patch("src.dev_workflow_mcp.server.register_phase_prompts")
    @patch("src.dev_workflow_mcp.server.register_discovery_prompts")
    def test_main_with_repository_path(
        self,
        mock_register_discovery,
        mock_register_phase,
        mock_init_config,
        mock_fastmcp,
    ):
        """Test main function with repository path specified."""
        # Mock FastMCP instance
        mock_mcp_instance = Mock()
        mock_fastmcp.return_value = mock_mcp_instance

        # Mock configuration service
        mock_config_service = Mock()
        mock_legacy_config = Mock()
        mock_config_service.to_legacy_server_config.return_value = mock_legacy_config
        mock_init_config.return_value = mock_config_service

        # Mock sys.argv to provide repository path
        test_args = ["server.py", "--repository-path", "/test/path"]
        with patch.object(sys, "argv", test_args):
            result = main()

        # Verify configuration service was initialized
        mock_init_config.assert_called_once()

        # Verify other calls
        mock_fastmcp.assert_called_once_with("Development Workflow")
        mock_register_phase.assert_called_once_with(
            mock_mcp_instance, mock_legacy_config
        )
        mock_register_discovery.assert_called_once_with(
            mock_mcp_instance, mock_legacy_config
        )
        mock_mcp_instance.run.assert_called_once_with(transport="stdio")

        assert result == 0

    @patch("src.dev_workflow_mcp.server.initialize_configuration_service")
    @patch("builtins.print")
    def test_main_with_invalid_repository_path(self, mock_print, mock_init_config):
        """Test main function with invalid repository path."""
        # Mock configuration service to raise validation error
        from src.dev_workflow_mcp.services.config_service import (
            ConfigurationValidationError,
        )

        mock_init_config.side_effect = ConfigurationValidationError(
            "Configuration validation failed: ['Repository path does not exist: /invalid/path']"
        )

        # Mock sys.argv to provide invalid path
        test_args = ["server.py", "--repository-path", "/invalid/path"]
        with patch.object(sys, "argv", test_args):
            result = main()

        # Verify error handling
        mock_init_config.assert_called_once()
        mock_print.assert_called_once_with(
            "Error: Configuration validation failed: ['Repository path does not exist: /invalid/path']"
        )

        # Verify error return code
        assert result == 1


class TestServerIntegration:
    """Test server integration and tool registration."""

    @pytest.mark.asyncio
    async def test_server_creation_and_tool_registration(self):
        """Test that server can be created and tools registered correctly."""
        from fastmcp import FastMCP

        from src.dev_workflow_mcp.config import ServerConfig
        from src.dev_workflow_mcp.prompts.discovery_prompts import (
            register_discovery_prompts,
        )
        from src.dev_workflow_mcp.prompts.phase_prompts import register_phase_prompts

        # Create a test config with current directory
        config = ServerConfig(".")

        # Create MCP server
        mcp = FastMCP("Test Development Workflow")

        # Register tools with config
        register_phase_prompts(mcp, config)
        register_discovery_prompts(mcp, config)

        # Verify tools are registered
        tools = await mcp.get_tools()

        expected_tools = [
            "workflow_guidance",
            "workflow_state",
            "workflow_discovery",
            "workflow_creation_guidance",
            "list_available_workflows",
            "validate_workflow_file",
        ]

        for tool_name in expected_tools:
            assert tool_name in tools, f"Tool {tool_name} not found in registered tools"

    @pytest.mark.asyncio
    async def test_workflow_discovery_with_config(self):
        """Test that workflow_discovery works with server config."""
        from fastmcp import FastMCP

        from src.dev_workflow_mcp.config import ServerConfig
        from src.dev_workflow_mcp.prompts.discovery_prompts import (
            register_discovery_prompts,
        )

        # Create config and server
        config = ServerConfig(".")
        mcp = FastMCP("Test")
        register_discovery_prompts(mcp, config)

        # Get and test the workflow_discovery tool
        tools = await mcp.get_tools()
        discovery_tool = tools["workflow_discovery"]

        # Call the discovery function (should now use server-side discovery)
        result = discovery_tool.fn(task_description="Test task")

        # Verify it returns discovery results instead of agent instructions
        assert isinstance(result, dict)
        assert "status" in result
        # Should be either "workflows_discovered", "no_workflows_found", "discovery_error", or "session_conflict_detected"
        assert result["status"] in [
            "workflows_discovered",
            "no_workflows_found",
            "discovery_error",
            "session_conflict_detected",
        ]


class TestToolStructures:
    """Test tool registration and structure after refactoring."""

    @pytest.mark.asyncio
    async def test_workflow_guidance_tool_structure(self):
        """Test workflow_guidance tool structure."""
        from fastmcp import FastMCP

        from src.dev_workflow_mcp.config import ServerConfig
        from src.dev_workflow_mcp.prompts.phase_prompts import register_phase_prompts

        config = ServerConfig(".")
        mcp = FastMCP("Test")
        register_phase_prompts(mcp, config)

        tools = await mcp.get_tools()
        assert "workflow_guidance" in tools
        workflow_tool = tools["workflow_guidance"]

        # Verify tool structure
        assert workflow_tool.name == "workflow_guidance"
        assert "Pure schema-driven workflow guidance" in workflow_tool.description
        assert "task_description" in workflow_tool.parameters["properties"]
        assert "action" in workflow_tool.parameters["properties"]
        assert "task_description" in workflow_tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_workflow_discovery_tool_structure(self):
        """Test workflow_discovery tool structure after modification."""
        from fastmcp import FastMCP

        from src.dev_workflow_mcp.config import ServerConfig
        from src.dev_workflow_mcp.prompts.discovery_prompts import (
            register_discovery_prompts,
        )

        config = ServerConfig(".")
        mcp = FastMCP("Test")
        register_discovery_prompts(mcp, config)

        tools = await mcp.get_tools()
        assert "workflow_discovery" in tools
        discovery_tool = tools["workflow_discovery"]

        # Verify tool structure
        assert discovery_tool.name == "workflow_discovery"
        assert "Discover available workflows" in discovery_tool.description
        assert "task_description" in discovery_tool.parameters["properties"]
        assert "workflows_dir" in discovery_tool.parameters["properties"]
        assert "task_description" in discovery_tool.parameters["required"]


class TestAutomaticCacheRestoration:
    """Test automatic cache restoration functionality during server startup."""

    @patch("src.dev_workflow_mcp.server.FastMCP")
    @patch("src.dev_workflow_mcp.server.initialize_configuration_service")
    @patch("src.dev_workflow_mcp.server.register_phase_prompts")
    @patch("src.dev_workflow_mcp.server.register_discovery_prompts")
    @patch(
        "src.dev_workflow_mcp.utils.session_manager.auto_restore_sessions_on_startup"
    )
    @patch("builtins.print")
    def test_main_with_cache_enabled_successful_restoration(
        self,
        mock_print,
        mock_auto_restore,
        mock_register_discovery,
        mock_register_phase,
        mock_init_config,
        mock_fastmcp,
    ):
        """Test main function with cache enabled and successful restoration."""
        # Mock FastMCP instance
        mock_mcp_instance = Mock()
        mock_fastmcp.return_value = mock_mcp_instance

        # Mock configuration service
        mock_config_service = Mock()
        mock_legacy_config = Mock()
        mock_config_service.to_legacy_server_config.return_value = mock_legacy_config
        mock_init_config.return_value = mock_config_service

        # Mock successful restoration
        mock_auto_restore.return_value = 3

        # Mock sys.argv with cache enabled
        test_args = ["server.py", "--enable-cache-mode"]
        with patch.object(sys, "argv", test_args):
            result = main()

        # Verify cache restoration was called
        mock_auto_restore.assert_called_once()

        # Verify success message was printed
        mock_print.assert_called_with(
            "Info: Automatically restored 3 workflow session(s) from cache"
        )

        # Verify server started normally
        mock_mcp_instance.run.assert_called_once_with(transport="stdio")
        assert result == 0

    @patch("src.dev_workflow_mcp.server.FastMCP")
    @patch("src.dev_workflow_mcp.server.initialize_configuration_service")
    @patch("src.dev_workflow_mcp.server.register_phase_prompts")
    @patch("src.dev_workflow_mcp.server.register_discovery_prompts")
    @patch(
        "src.dev_workflow_mcp.utils.session_manager.auto_restore_sessions_on_startup"
    )
    @patch("builtins.print")
    def test_main_with_cache_enabled_no_sessions_to_restore(
        self,
        mock_print,
        mock_auto_restore,
        mock_register_discovery,
        mock_register_phase,
        mock_init_config,
        mock_fastmcp,
    ):
        """Test main function with cache enabled but no sessions to restore."""
        # Mock FastMCP instance
        mock_mcp_instance = Mock()
        mock_fastmcp.return_value = mock_mcp_instance

        # Mock configuration service
        mock_config_service = Mock()
        mock_legacy_config = Mock()
        mock_config_service.to_legacy_server_config.return_value = mock_legacy_config
        mock_init_config.return_value = mock_config_service

        # Mock no sessions to restore
        mock_auto_restore.return_value = 0

        # Mock sys.argv with cache enabled
        test_args = ["server.py", "--enable-cache-mode"]
        with patch.object(sys, "argv", test_args):
            result = main()

        # Verify cache restoration was called
        mock_auto_restore.assert_called_once()

        # Verify no success message was printed (since restored_count is 0)
        mock_print.assert_not_called()

        # Verify server started normally
        mock_mcp_instance.run.assert_called_once_with(transport="stdio")
        assert result == 0

    @patch("src.dev_workflow_mcp.server.FastMCP")
    @patch("src.dev_workflow_mcp.server.initialize_configuration_service")
    @patch("src.dev_workflow_mcp.server.register_phase_prompts")
    @patch("src.dev_workflow_mcp.server.register_discovery_prompts")
    @patch(
        "src.dev_workflow_mcp.utils.session_manager.auto_restore_sessions_on_startup"
    )
    @patch("builtins.print")
    def test_main_with_cache_enabled_restoration_failure(
        self,
        mock_print,
        mock_auto_restore,
        mock_register_discovery,
        mock_register_phase,
        mock_init_config,
        mock_fastmcp,
    ):
        """Test main function with cache enabled but restoration failure."""
        # Mock FastMCP instance
        mock_mcp_instance = Mock()
        mock_fastmcp.return_value = mock_mcp_instance

        # Mock configuration service
        mock_config_service = Mock()
        mock_legacy_config = Mock()
        mock_config_service.to_legacy_server_config.return_value = mock_legacy_config
        mock_init_config.return_value = mock_config_service

        # Mock restoration failure
        mock_auto_restore.side_effect = Exception("Cache connection failed")

        # Mock sys.argv with cache enabled
        test_args = ["server.py", "--enable-cache-mode"]
        with patch.object(sys, "argv", test_args):
            result = main()

        # Verify cache restoration was attempted
        mock_auto_restore.assert_called_once()

        # Verify error message was printed
        mock_print.assert_called_with(
            "Info: Automatic cache restoration skipped: Cache connection failed"
        )

        # Verify server started normally despite restoration failure
        mock_mcp_instance.run.assert_called_once_with(transport="stdio")
        assert result == 0

    @patch("src.dev_workflow_mcp.server.FastMCP")
    @patch("src.dev_workflow_mcp.server.initialize_configuration_service")
    @patch("src.dev_workflow_mcp.server.register_phase_prompts")
    @patch("src.dev_workflow_mcp.server.register_discovery_prompts")
    def test_main_with_cache_disabled_no_restoration(
        self,
        mock_register_discovery,
        mock_register_phase,
        mock_init_config,
        mock_fastmcp,
    ):
        """Test main function with cache disabled - no restoration should occur."""
        # Mock FastMCP instance
        mock_mcp_instance = Mock()
        mock_fastmcp.return_value = mock_mcp_instance

        # Mock configuration service
        mock_config_service = Mock()
        mock_legacy_config = Mock()
        mock_config_service.to_legacy_server_config.return_value = mock_legacy_config
        mock_init_config.return_value = mock_config_service

        # Mock sys.argv without cache enabled
        test_args = ["server.py"]
        with (
            patch.object(sys, "argv", test_args),
            patch(
                "src.dev_workflow_mcp.utils.session_manager.auto_restore_sessions_on_startup"
            ) as mock_auto_restore,
        ):
            result = main()

            # Verify cache restoration was NOT called
            mock_auto_restore.assert_not_called()

        # Verify server started normally
        mock_mcp_instance.run.assert_called_once_with(transport="stdio")
        assert result == 0

    def test_auto_restore_sessions_on_startup_function_exists(self):
        """Test that the auto_restore_sessions_on_startup function exists and is importable."""
        try:
            from src.dev_workflow_mcp.utils.session_manager import (
                auto_restore_sessions_on_startup,
            )

            # Verify it's callable
            assert callable(auto_restore_sessions_on_startup)

            # Verify function signature (should return int)
            import inspect

            sig = inspect.signature(auto_restore_sessions_on_startup)
            assert len(sig.parameters) == 0  # No parameters expected

        except ImportError:
            pytest.fail(
                "auto_restore_sessions_on_startup function should be importable"
            )
