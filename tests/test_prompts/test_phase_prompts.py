"""Tests for phase prompt registration and functionality."""

from unittest.mock import Mock

import pytest
from fastmcp import Context, FastMCP

from src.dev_workflow_mcp.prompts.phase_prompts import register_phase_prompts


class TestPhasePrompts:
    """Test phase prompt registration and functionality."""

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

    def test_register_phase_prompts(self, mock_mcp):
        """Test that register_phase_prompts registers all expected tools."""
        # Call the registration function
        register_phase_prompts(mock_mcp)

        # Verify that mcp.tool() was called for each prompt function
        assert mock_mcp.tool.call_count == 6  # 6 prompt functions

        # Verify the decorator was called (tool registration)
        mock_mcp.tool.assert_called()

    @pytest.mark.asyncio
    async def test_phase_prompts_registration(self):
        """Test that all phase prompts are registered correctly."""
        mcp = FastMCP("test-server")
        register_phase_prompts(mcp)

        tools = await mcp.get_tools()

        expected_tools = [
            "init_workflow_guidance",
            "analyze_phase_guidance",
            "blueprint_phase_guidance",
            "construct_phase_guidance",
            "validate_phase_guidance",
            "revise_blueprint_guidance",
        ]

        for tool_name in expected_tools:
            assert tool_name in tools, f"Tool {tool_name} not registered"

    @pytest.mark.asyncio
    async def test_init_workflow_guidance_output(self, mock_context):
        """Test init_workflow_guidance output format."""
        mcp = FastMCP("test-server")
        register_phase_prompts(mcp)

        tools = await mcp.get_tools()
        init_tool = tools["init_workflow_guidance"]

        task = "Test task description"
        result = init_tool.fn(task_description=task, ctx=mock_context)

        assert "WORKFLOW INITIALIZED" in result
        assert task in result
        assert "analyze_phase_guidance" in result

    @pytest.mark.asyncio
    async def test_analyze_phase_guidance_output(self, mock_context):
        """Test analyze_phase_guidance output format."""
        mcp = FastMCP("test-server")
        register_phase_prompts(mcp)

        tools = await mcp.get_tools()
        analyze_tool = tools["analyze_phase_guidance"]

        task = "Test task description"
        result = analyze_tool.fn(task_description=task, ctx=mock_context)

        assert "ANALYZE PHASE" in result
        assert task in result
        assert "NO CODING OR PLANNING YET" in result
        assert "blueprint_phase_guidance" in result

    @pytest.mark.asyncio
    async def test_blueprint_phase_guidance_output(self, mock_context):
        """Test blueprint_phase_guidance output format."""
        mcp = FastMCP("test-server")
        register_phase_prompts(mcp)

        tools = await mcp.get_tools()
        blueprint_tool = tools["blueprint_phase_guidance"]

        task = "Test task description"
        summary = "Test requirements summary"
        result = blueprint_tool.fn(
            task_description=task, requirements_summary=summary, ctx=mock_context
        )

        assert "BLUEPRINT PHASE" in result
        assert task in result
        assert summary in result
        assert "construct_phase_guidance" in result
        assert "revise_blueprint_guidance" in result

    @pytest.mark.asyncio
    async def test_construct_phase_guidance_output(self, mock_context):
        """Test construct_phase_guidance output format."""
        mcp = FastMCP("test-server")
        register_phase_prompts(mcp)

        tools = await mcp.get_tools()
        construct_tool = tools["construct_phase_guidance"]

        task = "Test task description"
        result = construct_tool.fn(task_description=task, ctx=mock_context)

        assert "CONSTRUCT PHASE" in result
        assert task in result
        assert "IMPLEMENTATION" in result
        assert "validate_phase_guidance" in result

    @pytest.mark.asyncio
    async def test_validate_phase_guidance_output(self, mock_context):
        """Test validate_phase_guidance output format."""
        mcp = FastMCP("test-server")
        register_phase_prompts(mcp)

        tools = await mcp.get_tools()
        validate_tool = tools["validate_phase_guidance"]

        task = "Test task description"
        result = validate_tool.fn(task_description=task, ctx=mock_context)

        assert "VALIDATE PHASE" in result
        assert task in result
        assert "FINAL VERIFICATION" in result
        assert "complete_workflow_guidance" in result

    @pytest.mark.asyncio
    async def test_revise_blueprint_guidance_output(self, mock_context):
        """Test revise_blueprint_guidance output format."""
        mcp = FastMCP("test-server")
        register_phase_prompts(mcp)

        tools = await mcp.get_tools()
        revise_tool = tools["revise_blueprint_guidance"]

        task = "Test task description"
        feedback = "Test feedback"
        result = revise_tool.fn(
            task_description=task, feedback=feedback, ctx=mock_context
        )

        assert "REVISING BLUEPRINT" in result
        assert task in result
        assert feedback in result
        assert "construct_phase_guidance" in result

    @pytest.mark.asyncio
    async def test_tool_parameters(self):
        """Test that tools have correct parameter definitions."""
        mcp = FastMCP("test-server")
        register_phase_prompts(mcp)

        tools = await mcp.get_tools()

        # Test init_workflow_guidance parameters
        init_tool = tools["init_workflow_guidance"]
        assert "task_description" in init_tool.parameters["properties"]
        assert "task_description" in init_tool.parameters["required"]

        # Test analyze_phase_guidance parameters
        analyze_tool = tools["analyze_phase_guidance"]
        assert "task_description" in analyze_tool.parameters["properties"]
        assert "project_config_path" in analyze_tool.parameters["properties"]
        assert "task_description" in analyze_tool.parameters["required"]

        # Test blueprint_phase_guidance parameters
        blueprint_tool = tools["blueprint_phase_guidance"]
        assert "task_description" in blueprint_tool.parameters["properties"]
        assert "requirements_summary" in blueprint_tool.parameters["properties"]
        assert "task_description" in blueprint_tool.parameters["required"]
        assert "requirements_summary" in blueprint_tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_workflow_chaining(self, mock_context):
        """Test that prompts reference the correct next prompts."""
        mcp = FastMCP("test-server")
        register_phase_prompts(mcp)
        tools = await mcp.get_tools()

        # Test init -> analyze chain
        init_result = tools["init_workflow_guidance"].fn(
            task_description="test", ctx=mock_context
        )
        assert "analyze_phase_guidance" in init_result

        # Test analyze -> blueprint chain
        analyze_result = tools["analyze_phase_guidance"].fn(
            task_description="test", ctx=mock_context
        )
        assert "blueprint_phase_guidance" in analyze_result

        # Test blueprint -> construct chain
        blueprint_result = tools["blueprint_phase_guidance"].fn(
            task_description="test", requirements_summary="summary", ctx=mock_context
        )
        assert "construct_phase_guidance" in blueprint_result

        # Test construct -> validate chain
        construct_result = tools["construct_phase_guidance"].fn(
            task_description="test", ctx=mock_context
        )
        assert "validate_phase_guidance" in construct_result

    @pytest.mark.asyncio
    async def test_error_handling_references(self, mock_context):
        """Test that prompts reference error handling correctly."""
        mcp = FastMCP("test-server")
        register_phase_prompts(mcp)
        tools = await mcp.get_tools()

        construct_result = tools["construct_phase_guidance"].fn(
            task_description="test", ctx=mock_context
        )
        assert "error_recovery_guidance" in construct_result

        validate_result = tools["validate_phase_guidance"].fn(
            task_description="test", ctx=mock_context
        )
        assert "fix_validation_issues_guidance" in validate_result

    @pytest.mark.asyncio
    async def test_all_prompts_contain_required_elements(self, mock_context):
        """Test that all prompts contain required workflow elements."""
        mcp = FastMCP("test-server")
        register_phase_prompts(mcp)
        tools = await mcp.get_tools()

        task = "test task"

        for tool_name, tool in tools.items():
            if (
                tool_name == "init_workflow_guidance"
                or tool_name == "analyze_phase_guidance"
            ):
                result = tool.fn(task_description=task, ctx=mock_context)
            elif tool_name == "blueprint_phase_guidance":
                result = tool.fn(
                    task_description=task,
                    requirements_summary="summary",
                    ctx=mock_context,
                )
            elif (
                tool_name == "construct_phase_guidance"
                or tool_name == "validate_phase_guidance"
            ):
                result = tool.fn(task_description=task, ctx=mock_context)
            elif tool_name == "revise_blueprint_guidance":
                result = tool.fn(
                    task_description=task, feedback="feedback", ctx=mock_context
                )
            else:
                continue

            # All prompts should contain task description
            assert task in result
            # All prompts should have clear action guidance
            assert (
                "REQUIRED ACTIONS" in result
                or "ACTIONS TO TAKE" in result
                or "NEXT STEP" in result
                or "Call:" in result
                or "call:" in result
            )

    @pytest.mark.asyncio
    async def test_mandatory_execution_emphasis(self, mock_context):
        """Test that all guidance tools emphasize mandatory execution."""
        mcp = FastMCP("test-server")
        register_phase_prompts(mcp)
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
            if (
                tool_name == "init_workflow_guidance"
                or tool_name == "analyze_phase_guidance"
            ):
                result = tool.fn(task_description=task, ctx=mock_context)
            elif tool_name == "blueprint_phase_guidance":
                result = tool.fn(
                    task_description=task,
                    requirements_summary="summary",
                    ctx=mock_context,
                )
            elif (
                tool_name == "construct_phase_guidance"
                or tool_name == "validate_phase_guidance"
            ):
                result = tool.fn(task_description=task, ctx=mock_context)
            elif tool_name == "revise_blueprint_guidance":
                result = tool.fn(
                    task_description=task, feedback="feedback", ctx=mock_context
                )
            else:
                continue

            assert (
                "REQUIRED ACTIONS" in result
                or "ACTIONS TO TAKE" in result
                or "NEXT STEP" in result
                or "Call:" in result
                or "call:" in result
            )
