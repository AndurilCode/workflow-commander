"""Tests for management prompt registration and functionality."""

from unittest.mock import Mock, patch

import pytest
from fastmcp import Context, FastMCP

from src.dev_workflow_mcp.prompts.management_prompts import register_management_prompts


class TestManagementPrompts:
    """Test management prompt registration and functionality."""

    @pytest.fixture
    def mock_mcp(self):
        """Create a mock FastMCP instance for testing."""
        mcp = Mock(spec=FastMCP)
        mcp.tool = Mock()
        return mcp

    @pytest.fixture
    def mock_context(self):
        """Create a mock Context instance for testing."""
        context = Mock(spec=Context)
        context.client_id = "test-client-123"
        return context

    def test_register_management_prompts(self, mock_mcp):
        """Test that register_management_prompts registers all expected tools."""
        # Call the registration function
        register_management_prompts(mock_mcp)

        # Verify that mcp.tool() was called for each prompt function
        assert mock_mcp.tool.call_count == 7  # 7 prompt functions

        # Verify the decorator was called (tool registration)
        mock_mcp.tool.assert_called()

    @pytest.mark.asyncio
    async def test_management_prompts_registration_with_real_mcp(self):
        """Test registration with a real FastMCP instance."""
        mcp = FastMCP("test-server")

        # Register the prompts
        register_management_prompts(mcp)

        # Get the registered tools
        tools = await mcp.get_tools()

        # Verify all expected prompt tools are registered
        expected_tools = [
            "complete_workflow_guidance",
            "iterate_next_item_guidance",
            "finalize_workflow_guidance",
            "error_recovery_guidance",
            "fix_validation_issues_guidance",
            "escalate_to_user_guidance",
            "changelog_update_guidance",
        ]

        for tool_name in expected_tools:
            assert tool_name in tools, f"Tool {tool_name} not registered"

    @pytest.mark.asyncio
    async def test_complete_workflow_guidance_output(self, mock_context):
        """Test complete_workflow_guidance output format."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)

        tools = await mcp.get_tools()
        complete_tool = tools["complete_workflow_guidance"]

        task = "Test task description"
        result = complete_tool.fn(task_description=task, ctx=mock_context)

        assert "WORKFLOW TASK COMPLETED" in result
        assert task in result
        assert "iterate_next_item_guidance" in result
        assert "finalize_workflow_guidance" in result
        assert "COMPLETED" in result

    @pytest.mark.asyncio
    async def test_iterate_next_item_guidance_output(self, mock_context):
        """Test iterate_next_item_guidance output format."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)

        tools = await mcp.get_tools()
        iterate_tool = tools["iterate_next_item_guidance"]

        result = iterate_tool.fn(ctx=mock_context)

        assert (
            "PROCESSING NEXT WORKFLOW ITEM" in result
            or "NO MORE ITEMS TO PROCESS" in result
        )
        assert (
            "analyze_phase_guidance" in result or "finalize_workflow_guidance" in result
        )

    @pytest.mark.asyncio
    async def test_finalize_workflow_guidance_output(self, mock_context):
        """Test finalize_workflow_guidance output format."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)

        tools = await mcp.get_tools()
        finalize_tool = tools["finalize_workflow_guidance"]

        result = finalize_tool.fn(ctx=mock_context)

        assert "WORKFLOW FINALIZED" in result
        assert "INIT" in result
        assert "READY" in result
        assert "WORKFLOW COMPLETE" in result

    @pytest.mark.asyncio
    @patch("src.dev_workflow_mcp.prompts.management_prompts.sync_session_to_s3")
    async def test_finalize_workflow_with_s3_sync(self, mock_sync, mock_context):
        """Test that finalization triggers S3 sync."""
        # Mock successful S3 sync
        mock_sync.return_value = "s3://test-bucket/workflow-states/archived/test-client-123/2025/05/29/133045_workflow_final.json"

        mcp = FastMCP("test-server")
        register_management_prompts(mcp)

        tools = await mcp.get_tools()
        finalize_tool = tools["finalize_workflow_guidance"]

        result = finalize_tool.fn(ctx=mock_context)

        # Verify S3 sync was called with archive=True
        mock_sync.assert_called_once_with("test-client-123", archive=True)

        # Verify S3 key is in the output
        assert "Workflow archived to S3" in result
        assert "s3://test-bucket" in result

    @pytest.mark.asyncio
    async def test_error_recovery_guidance_output(self, mock_context):
        """Test error_recovery_guidance output format."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)

        tools = await mcp.get_tools()
        error_tool = tools["error_recovery_guidance"]

        task = "Test task"
        error_details = "Test error occurred"
        result = error_tool.fn(
            task_description=task, error_details=error_details, ctx=mock_context
        )

        assert "ERROR RECOVERY MODE" in result
        assert task in result
        assert error_details in result
        assert "construct_phase_guidance" in result
        assert "blueprint_phase_guidance" in result
        assert "escalate_to_user_guidance" in result

    @pytest.mark.asyncio
    async def test_fix_validation_issues_guidance_output(self, mock_context):
        """Test fix_validation_issues_guidance output format."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)

        tools = await mcp.get_tools()
        fix_tool = tools["fix_validation_issues_guidance"]

        task = "Test task"
        issues = "Test validation issues"
        result = fix_tool.fn(task_description=task, issues=issues, ctx=mock_context)

        assert "FIXING VALIDATION ISSUES" in result
        assert task in result
        assert issues in result
        assert "validate_phase_guidance" in result
        assert "error_recovery_guidance" in result

    @pytest.mark.asyncio
    async def test_escalate_to_user_guidance_output(self, mock_context):
        """Test escalate_to_user_guidance output format."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)

        tools = await mcp.get_tools()
        escalate_tool = tools["escalate_to_user_guidance"]

        task = "Test task"
        error_details = "Critical error details"
        result = escalate_tool.fn(
            task_description=task, error_details=error_details, ctx=mock_context
        )

        assert "ESCALATING TO USER" in result
        assert task in result
        assert error_details in result
        assert "ERROR" in result
        assert "construct_phase_guidance" in result

    @pytest.mark.asyncio
    async def test_changelog_update_guidance_output(self, mock_context):
        """Test changelog_update_guidance output format."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)

        tools = await mcp.get_tools()
        changelog_tool = tools["changelog_update_guidance"]

        task = "Test task"
        result = changelog_tool.fn(task_description=task, ctx=mock_context)

        assert "UPDATING PROJECT CHANGELOG" in result
        assert task in result
        assert "project_config.md" in result
        assert "## Changelog" in result

    @pytest.mark.asyncio
    async def test_changelog_update_guidance_with_custom_path(self, mock_context):
        """Test changelog_update_guidance with custom project config path."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)

        tools = await mcp.get_tools()
        changelog_tool = tools["changelog_update_guidance"]

        task = "Test task"
        config_path = "custom_config.md"
        result = changelog_tool.fn(
            task_description=task, project_config_path=config_path, ctx=mock_context
        )

        assert config_path in result
        assert "Read custom_config.md" in result or config_path in result

    @pytest.mark.asyncio
    async def test_error_recovery_decision_paths(self, mock_context):
        """Test that error_recovery_guidance contains all decision paths."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)

        tools = await mcp.get_tools()
        error_tool = tools["error_recovery_guidance"]

        result = error_tool.fn(
            task_description="test", error_details="error", ctx=mock_context
        )

        # Should contain all three recovery paths
        assert "construct_phase_guidance" in result
        assert "blueprint_phase_guidance" in result
        assert "escalate_to_user_guidance" in result

    @pytest.mark.asyncio
    async def test_workflow_completion_chain(self, mock_context):
        """Test the workflow completion chain logic."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)
        tools = await mcp.get_tools()

        # Test complete -> iterate chain
        complete_result = tools["complete_workflow_guidance"].fn(
            task_description="test", ctx=mock_context
        )
        assert "iterate_next_item_guidance" in complete_result
        assert "finalize_workflow_guidance" in complete_result

        # Test iterate -> analyze chain
        iterate_result = tools["iterate_next_item_guidance"].fn(ctx=mock_context)
        assert (
            "analyze_phase_guidance" in iterate_result
            or "finalize_workflow_guidance" in iterate_result
        )

    @pytest.mark.asyncio
    async def test_error_handling_chains(self, mock_context):
        """Test error handling prompt chains."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)
        tools = await mcp.get_tools()

        # Test error recovery chains
        error_result = tools["error_recovery_guidance"].fn(
            task_description="test", error_details="error", ctx=mock_context
        )
        assert "construct_phase_guidance" in error_result
        assert "blueprint_phase_guidance" in error_result
        assert "escalate_to_user_guidance" in error_result

        # Test validation fix chains
        fix_result = tools["fix_validation_issues_guidance"].fn(
            task_description="test", issues="issues", ctx=mock_context
        )
        assert "validate_phase_guidance" in fix_result
        assert "error_recovery_guidance" in fix_result

    @pytest.mark.asyncio
    async def test_all_prompts_contain_required_elements(self, mock_context):
        """Test that all prompts contain required workflow elements."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)
        tools = await mcp.get_tools()

        task = "test task"

        for tool_name, tool in tools.items():
            if tool_name == "complete_workflow_guidance":
                result = tool.fn(task_description=task, ctx=mock_context)
            elif (
                tool_name == "iterate_next_item_guidance"
                or tool_name == "finalize_workflow_guidance"
            ):
                result = tool.fn(ctx=mock_context)
            elif tool_name == "error_recovery_guidance":
                result = tool.fn(
                    task_description=task, error_details="error", ctx=mock_context
                )
            elif tool_name == "fix_validation_issues_guidance":
                result = tool.fn(
                    task_description=task, issues="issues", ctx=mock_context
                )
            elif tool_name == "escalate_to_user_guidance":
                result = tool.fn(
                    task_description=task, error_details="error", ctx=mock_context
                )
            elif tool_name == "changelog_update_guidance":
                result = tool.fn(task_description=task, ctx=mock_context)
            else:
                continue

            # All prompts should have clear action guidance (except finalize which is the end)
            if tool_name != "finalize_workflow_guidance":
                assert (
                    "ACTIONS" in result
                    or "ACTION" in result
                    or "REQUIRED" in result
                    or "NEXT STEP" in result
                    or "NEXT STEPS" in result
                    or "Call:" in result
                    or "call:" in result
                )

    @pytest.mark.asyncio
    async def test_prompt_parameter_handling(self, mock_context):
        """Test that prompts handle parameters correctly."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)
        tools = await mcp.get_tools()

        # Test with different parameter combinations
        task = "complex task with special characters: @#$%"
        error = "complex error with newlines\nand special chars: <>[]"

        error_result = tools["error_recovery_guidance"].fn(
            task_description=task, error_details=error, ctx=mock_context
        )
        assert task in error_result
        assert error in error_result

        fix_result = tools["fix_validation_issues_guidance"].fn(
            task_description=task, issues=error, ctx=mock_context
        )
        assert task in fix_result
        assert error in fix_result

    @pytest.mark.asyncio
    async def test_escalation_workflow(self, mock_context):
        """Test the escalation workflow for critical errors."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)
        tools = await mcp.get_tools()

        escalate_result = tools["escalate_to_user_guidance"].fn(
            task_description="test", error_details="critical error", ctx=mock_context
        )

        assert "ESCALATING TO USER" in escalate_result
        assert "ERROR" in escalate_result
        assert "critical error" in escalate_result
        assert "construct_phase_guidance" in escalate_result

    @pytest.mark.asyncio
    async def test_tool_parameters(self):
        """Test that tools have correct parameter definitions."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)

        tools = await mcp.get_tools()

        # Test complete_workflow_guidance parameters
        complete_tool = tools["complete_workflow_guidance"]
        assert "task_description" in complete_tool.parameters["properties"]
        assert "task_description" in complete_tool.parameters["required"]

        # Test error_recovery_guidance parameters
        error_tool = tools["error_recovery_guidance"]
        assert "task_description" in error_tool.parameters["properties"]
        assert "error_details" in error_tool.parameters["properties"]
        assert "task_description" in error_tool.parameters["required"]
        assert "error_details" in error_tool.parameters["required"]

        # Test changelog_update_guidance parameters
        changelog_tool = tools["changelog_update_guidance"]
        assert "task_description" in changelog_tool.parameters["properties"]
        assert "project_config_path" in changelog_tool.parameters["properties"]
        assert "task_description" in changelog_tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_mandatory_execution_emphasis(self, mock_context):
        """Test that all guidance tools emphasize mandatory execution."""
        mcp = FastMCP("test-server")
        register_management_prompts(mcp)
        tools = await mcp.get_tools()

        # Check that tool descriptions emphasize mandatory execution
        for _tool_name, tool in tools.items():
            assert (
                "mandatory" in tool.description.lower()
                or "guide" in tool.description.lower()
            )

        # Check that tool responses contain required actions
        task = "test task"
        for tool_name, tool in tools.items():
            if tool_name == "complete_workflow_guidance":
                result = tool.fn(task_description=task, ctx=mock_context)
            elif (
                tool_name == "iterate_next_item_guidance"
                or tool_name == "finalize_workflow_guidance"
            ):
                result = tool.fn(ctx=mock_context)
            elif tool_name == "error_recovery_guidance":
                result = tool.fn(
                    task_description=task, error_details="error", ctx=mock_context
                )
            elif tool_name == "fix_validation_issues_guidance":
                result = tool.fn(
                    task_description=task, issues="issues", ctx=mock_context
                )
            elif tool_name == "escalate_to_user_guidance":
                result = tool.fn(
                    task_description=task, error_details="error", ctx=mock_context
                )
            elif tool_name == "changelog_update_guidance":
                result = tool.fn(task_description=task, ctx=mock_context)
            else:
                continue

            # All guidance tools should contain step guidance (except finalize which is the end)
            if tool_name != "finalize_workflow_guidance":
                assert (
                    "NEXT STEP" in result
                    or "WHEN" in result
                    or "AFTER" in result
                    or "Call:" in result
                    or "call:" in result
                )
