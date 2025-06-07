"""Pure schema-driven workflow prompts.

This module provides workflow guidance based purely on YAML workflow schemas.
No hardcoded logic - all behavior determined by workflow definitions.
"""

import json

from fastmcp import Context, FastMCP
from pydantic import Field

from ..utils.session_id_utils import (
    add_session_id_to_response,
)
from ..utils.session_manager import (
    add_log_to_session,
    create_dynamic_session,
    export_session_to_markdown,
    get_dynamic_session_workflow_def,
    get_or_create_dynamic_session,
    get_session,
    get_session_type,
    list_cached_sessions,
    store_workflow_definition_in_cache,
    update_dynamic_session_node,
    update_dynamic_session_status,
)
from ..utils.workflow_engine import WorkflowEngine
from ..utils.yaml_loader import WorkflowLoader
from .evidence_extraction import extract_automatic_evidence_from_session
from .formatting import (
    format_enhanced_node_status,
    format_yaml_error_guidance,
    generate_node_completion_outputs,
)
from .session_resolution import resolve_session_context
from .validation import validate_task_description
from .yaml_parsing import (
    parse_and_validate_yaml_context,
    parse_criteria_evidence_context,
)

# Import functions that tests expect to be available in this module

# =============================================================================
# WORKFLOW HANDLERS
# =============================================================================


def _handle_dynamic_workflow(
    session,
    workflow_def,
    action: str,
    context: str,
    engine: WorkflowEngine,
    loader: WorkflowLoader,
) -> str:
    """Handle dynamic workflow execution."""
    current_node_name = session.current_node

    if action.lower() == "next":
        # Extract choice and criteria evidence from context
        choice, criteria_evidence, user_approval = parse_criteria_evidence_context(
            context
        )

        if choice:
            # Validate the transition
            current_node = workflow_def.workflow.tree.get(current_node_name)
            if not current_node:
                return f"❌ **Invalid State:** Current node '{current_node_name}' not found in workflow"

            # Check if transition is valid
            next_allowed_nodes = getattr(current_node, "next_allowed_nodes", [])
            if choice not in next_allowed_nodes:
                return f"❌ **Invalid Transition:** Cannot transition from '{current_node_name}' to '{choice}'"

            # Check if target node requires approval
            target_node = workflow_def.workflow.tree.get(choice)
            if (
                target_node
                and getattr(target_node, "needs_approval", False)
                and not user_approval
            ):
                return f"❌ **Approval Required:** Transition to '{choice}' requires explicit user approval. Include \"user_approval\": true in your context."

            # Generate node completion outputs if criteria evidence provided
            if criteria_evidence:
                generate_node_completion_outputs(
                    current_node_name, current_node, session, criteria_evidence
                )

            # If no criteria evidence provided, try automatic extraction
            if not criteria_evidence and current_node:
                acceptance_criteria = getattr(current_node, "acceptance_criteria", {})
                if acceptance_criteria:
                    criteria_evidence = extract_automatic_evidence_from_session(
                        session, current_node_name, acceptance_criteria
                    )

            # Update session
            update_dynamic_session_node(session.session_id, choice, workflow_def)

            # Log the transition with evidence
            if criteria_evidence:
                evidence_summary = ", ".join(
                    f"{k}: {v[:50]}..." for k, v in criteria_evidence.items()
                )
                log_message = f"Transitioned from {current_node_name} to {choice} with evidence: {evidence_summary}"
            else:
                log_message = f"Transitioned from {current_node_name} to {choice}"

            add_log_to_session(session.session_id, log_message)

            # Get updated session and display new node status
            updated_session = get_session(session.session_id)
            new_node = workflow_def.workflow.tree.get(choice)

            if new_node:
                return format_enhanced_node_status(
                    new_node, workflow_def, updated_session
                )
            else:
                return f"❌ **Error:** Target node '{choice}' not found in workflow definition"
        else:
            return "❌ **Missing Choice:** Please specify which node to transition to using context format"

    else:
        # Display current node status
        current_node = workflow_def.workflow.tree.get(current_node_name)
        if current_node:
            return format_enhanced_node_status(current_node, workflow_def, session)
        else:
            return f"❌ **Invalid State:** Current node '{current_node_name}' not found in workflow"


# =============================================================================
# CACHE HANDLERS
# =============================================================================


def _handle_cache_restore_operation(client_id: str) -> str:
    """Handle cache restore operation."""
    try:
        from ..utils.session_manager import restore_sessions_from_cache

        restored_count = restore_sessions_from_cache(client_id)
        return f"✅ **Cache Restore Complete:** Restored {restored_count} sessions from cache for client '{client_id}'"
    except Exception as e:
        return f"❌ Error restoring cache: {str(e)}"


def _handle_cache_list_operation(client_id: str) -> str:
    """Handle cache list operation."""
    try:
        sessions = list_cached_sessions(client_id)
        if not sessions:
            return f"📭 No cached sessions found for client '{client_id}'"

        result = f"📋 **Cached Sessions for client '{client_id}':**\n\n"
        for session in sessions:
            if "total_cached_sessions" in session:
                # This is cache stats
                result += "**Cache Statistics:**\n"
                result += f"- Total cached sessions: {session.get('total_cached_sessions', 0)}\n"
                result += f"- Active sessions: {session.get('active_sessions', 0)}\n"
                result += (
                    f"- Completed sessions: {session.get('completed_sessions', 0)}\n"
                )
                if session.get("oldest_entry"):
                    result += f"- Oldest entry: {session['oldest_entry']}\n"
                if session.get("newest_entry"):
                    result += f"- Newest entry: {session['newest_entry']}\n"
            else:
                # Individual session info
                result += f"**Session: {session['session_id'][:8]}...**\n"
                result += f"- Workflow: {session.get('workflow_name', 'Unknown')}\n"
                result += f"- Status: {session.get('status', 'Unknown')}\n"
                result += f"- Current Node: {session.get('current_node', 'Unknown')}\n"
                result += (
                    f"- Task: {session.get('task_description', 'No description')}\n"
                )
                result += f"- Created: {session.get('created_at', 'Unknown')}\n"
                result += f"- Updated: {session.get('last_updated', 'Unknown')}\n\n"

        return result

    except Exception as e:
        return f"❌ Error listing cached sessions: {str(e)}"


# =============================================================================
# TOOL REGISTRATION
# =============================================================================


def register_phase_prompts(app: FastMCP, config=None):
    """Register purely schema-driven workflow prompts.

    Args:
        app: FastMCP application instance
        config: ServerConfig instance with repository path settings (optional)
    """
    # Initialize session manager with server config for auto-sync
    if config:
        from ..utils.session_manager import set_server_config

        set_server_config(config)

    @app.tool()
    def workflow_guidance(
        task_description: str = Field(
            description="Task description in format 'Action: Brief description'"
        ),
        action: str = Field(
            default="",
            description="Workflow action: 'start', 'plan', 'build', 'revise', 'next'",
        ),
        context: str = Field(
            default="",
            description="🚨 MANDATORY CONTEXT FORMAT: When transitioning nodes, ALWAYS use JSON format with criteria evidence. "
            'PREFERRED: JSON format: \'{"choose": "node_name", "criteria_evidence": {"criterion1": "detailed evidence"}}\' - '
            "LEGACY: String format 'choose: node_name' (DISCOURAGED - provides poor work tracking). "
            "REQUIREMENT: Include specific evidence of actual work completed, not generic confirmations.",
        ),
        options: str = Field(
            default="",
            description="Optional parameters like project_config_path for specific actions",
        ),
        session_id: str = Field(
            default="",
            description="Optional session ID to target specific workflow session. "
            "🎯 **MULTI-SESSION SUPPORT**: Use this for parallel workflows or session continuity. "
            "Examples: workflow_guidance(session_id='abc-123', ...) to target specific session. "
            "If not provided, determines session from client context (backward compatibility). "
            "🔄 **BEST PRACTICE**: Always include session_id when working with multiple concurrent workflows.",
        ),
        ctx: Context = None,
    ) -> str:
        """Pure schema-driven workflow guidance.

        Provides guidance based entirely on workflow schema structure.
        No hardcoded behavior - everything driven by YAML definitions.

        🚨 CRITICAL AGENT REQUIREMENTS:
        - **MANDATORY**: When transitioning nodes, ALWAYS provide criteria_evidence in JSON format
        - **REQUIRED**: Use JSON context format: {"choose": "node_name", "criteria_evidence": {"criterion": "detailed evidence"}}
        - **NEVER**: Use simple string format "choose: node_name" - this provides poor tracking
        - **ALWAYS**: Include specific evidence of work completed for each acceptance criterion

        CRITICAL DISCOVERY-FIRST LOGIC:
        - If no session exists, FORCE discovery first regardless of action
        - Dynamic sessions continue with schema-driven workflow
        - Legacy only when YAML workflows unavailable

        🎯 AGENT EXECUTION STANDARDS:
        - Provide detailed evidence instead of generic confirmations
        - Document actual work performed, not just criterion names
        - Use JSON format for ALL node transitions to capture real work details
        """
        try:
            # Handle FieldInfo objects passed as default values
            if hasattr(action, "default"):
                action = action.default or ""
            if hasattr(context, "default"):
                context = context.default or ""
            if hasattr(options, "default"):
                options = options.default or ""
            if hasattr(session_id, "default"):
                session_id = session_id.default or ""

            # Resolve session using new session ID approach
            target_session_id, client_id = resolve_session_context(
                session_id, context, ctx
            )

            # Initialize workflow engine and loader
            engine = WorkflowEngine()
            loader = WorkflowLoader()

            # Determine session handling approach
            if target_session_id:
                # Explicit session ID provided - work with specific session
                session = get_session(target_session_id)
                if not session:
                    return add_session_id_to_response(
                        f"❌ **Session Not Found:** {target_session_id}\n\nThe specified session does not exist.",
                        target_session_id,
                    )
                session_type = "dynamic" if session else None
            else:
                # No explicit session - check for client sessions (backward compatibility)
                session_type = (
                    get_session_type(client_id) if client_id != "default" else None
                )

                # For backward compatibility, try to get any existing client session
                if session_type == "dynamic":
                    session = get_or_create_dynamic_session(client_id, task_description)
                    target_session_id = session.session_id if session else None
                else:
                    session = None

            if session_type == "dynamic" and session:
                # Continue with existing dynamic workflow
                workflow_def = get_dynamic_session_workflow_def(target_session_id)

                if not workflow_def:
                    return add_session_id_to_response(
                        f"""❌ **Missing Workflow Definition**

Dynamic session exists but workflow definition is missing.

**⚠️ DISCOVERY REQUIRED:**

1. **Discover workflows:** `workflow_discovery(task_description="{task_description}")`
2. **Start workflow:** Follow the discovery instructions to provide workflow YAML content""",
                        target_session_id,
                    )

                result = _handle_dynamic_workflow(
                    session, workflow_def, action, context, engine, loader
                )
                return add_session_id_to_response(result, target_session_id)

            else:
                # session_type is None - NO SESSION EXISTS
                # MANDATORY DISCOVERY-FIRST ENFORCEMENT

                if action.lower() == "start" and context and isinstance(context, str):
                    # Parse and validate YAML context
                    workflow_name, yaml_content, error_message = (
                        parse_and_validate_yaml_context(context)
                    )

                    if error_message:
                        return format_yaml_error_guidance(error_message, workflow_name)

                    # Validate task description format
                    try:
                        validated_description = validate_task_description(
                            task_description
                        )
                    except ValueError as e:
                        return f"❌ **Task Description Error:** {str(e)}"

                    # Load workflow definition
                    workflow_def = None

                    if not yaml_content and workflow_name:
                        # Only workflow name provided - load from yaml_loader
                        workflow_def = loader.get_workflow_with_cache_fallback(
                            workflow_name
                        )
                        if not workflow_def:
                            # Workflow not found - guide user
                            return f"""❌ **Workflow Not Found:** '{workflow_name}'

🔍 **Available Options:**

1. **Run discovery to see available workflows:**
   ```
   workflow_discovery(task_description="{task_description}")
   ```

2. **Check workflow files in:** `.workflow-commander/workflows/`

**💡 Note:** Ensure the workflow name matches exactly with available workflows."""

                    elif yaml_content:
                        # YAML content provided - parse it
                        try:
                            workflow_def = loader.load_workflow_from_string(
                                yaml_content, workflow_name
                            )
                            if not workflow_def:
                                return format_yaml_error_guidance(
                                    "YAML parsing failed: Invalid workflow structure",
                                    workflow_name,
                                )
                        except Exception as e:
                            return format_yaml_error_guidance(
                                f"YAML parsing failed: {str(e)}", workflow_name
                            )

                    else:
                        # No workflow name or YAML content
                        return format_yaml_error_guidance(
                            "Workflow name or YAML content is required",
                            workflow_name,
                        )

                    # Create new dynamic session
                    session = create_dynamic_session(
                        client_id=client_id,
                        task_description=validated_description,
                        workflow_def=workflow_def,
                    )

                    if not session:
                        return "❌ **Session Creation Failed:** Could not create workflow session"

                    # Store workflow definition in cache for the session
                    store_workflow_definition_in_cache(session.session_id, workflow_def)

                    # Set the session to start at the root node
                    root_node_name = workflow_def.workflow.root
                    update_dynamic_session_node(
                        session.session_id, root_node_name, workflow_def
                    )
                    update_dynamic_session_status(session.session_id, "RUNNING")

                    # Add log entry
                    add_log_to_session(
                        session.session_id,
                        f"Workflow '{workflow_name}' started at node '{root_node_name}'",
                    )

                    # Get the root node and display its status
                    root_node = workflow_def.workflow.tree.get(root_node_name)
                    if root_node:
                        result = (
                            f"✅ **Workflow Started:** {workflow_name}\n\n"
                            + format_enhanced_node_status(
                                root_node, workflow_def, session
                            )
                        )
                        return add_session_id_to_response(result, session.session_id)
                    else:
                        return add_session_id_to_response(
                            f"❌ **Configuration Error:** Root node '{root_node_name}' not found in workflow tree",
                            session.session_id,
                        )

                else:
                    # Force discovery first for any other action
                    return f"""🔍 **Workflow Discovery Required**

🚨 **MANDATORY:** No active workflow session found. You MUST discover and start a workflow first.

**📋 REQUIRED Steps:**

1. **Discover available workflows:**
   ```
   workflow_discovery(task_description="{task_description}")
   ```

2. **Start a workflow:** Follow the discovery instructions to select and start a workflow.

**⚠️ CRITICAL Note:** All workflow operations REQUIRE an active session. Discovery creates the foundation for workflow execution."""

        except Exception as e:
            return f"❌ **Workflow Guidance Error:** {str(e)}"

    @app.tool()
    def workflow_state(
        operation: str = Field(
            description="State operation: 'get' (current status), 'update' (modify state), 'reset' (clear state)"
        ),
        updates: str = Field(
            default="",
            description='JSON string with state updates for \'update\' operation. Example: \'{"phase": "CONSTRUCT", "status": "RUNNING"}\'',
        ),
        session_id: str = Field(
            default="",
            description="Optional session ID to target specific workflow session. "
            "🎯 **MULTI-SESSION SUPPORT**: Use this to track state for specific workflow sessions. "
            "Examples: workflow_state(operation='get', session_id='abc-123') to check specific session status. "
            "If not provided, determines session from client context (backward compatibility). "
            "🔄 **BEST PRACTICE**: Always include session_id when managing multiple concurrent workflows.",
        ),
        ctx: Context = None,
    ) -> str:
        """Get or update workflow state."""
        try:
            # Handle FieldInfo objects
            if hasattr(updates, "default"):
                updates = updates.default or ""
            if hasattr(session_id, "default"):
                session_id = session_id.default or ""

            # Resolve session
            target_session_id, client_id = resolve_session_context(session_id, "", ctx)

            if operation == "get":
                if target_session_id:
                    session = get_session(target_session_id)
                    if session:
                        state_info = export_session_to_markdown(session.client_id)
                        return add_session_id_to_response(
                            f"**Current Workflow State:**\n\n{state_info}",
                            target_session_id,
                        )
                    else:
                        return f"❌ **Session Not Found:** {target_session_id}"
                else:
                    return "❌ **No Active Workflow Session:** No workflow session found for state query"

            elif operation == "update":
                if not target_session_id:
                    return "❌ **No Active Workflow Session:** Cannot update state without an active session"

                if not updates:
                    return "❌ **Missing Updates:** No update data provided"

                try:
                    update_data = json.loads(updates)

                    # Add log entry for the update
                    log_entry = update_data.get("log_entry")
                    if log_entry:
                        add_log_to_session(target_session_id, log_entry)
                        return add_session_id_to_response(
                            f"✅ **State Updated:** {log_entry}", target_session_id
                        )
                    else:
                        return add_session_id_to_response(
                            "✅ **State Updated:** Update applied to session",
                            target_session_id,
                        )

                except json.JSONDecodeError:
                    return "❌ **Invalid JSON:** Updates must be valid JSON format"

            else:
                return f"❌ **Invalid Operation:** '{operation}' is not a valid operation. Use 'get' or 'update'"

        except Exception as e:
            return f"❌ **Workflow State Error:** {str(e)}"

    @app.tool()
    def workflow_cache_management(
        operation: str = Field(
            description="Cache operation: 'restore' (restore sessions from cache), 'list' (list cached sessions), 'stats' (cache statistics)"
        ),
        client_id: str = Field(
            default="default",
            description="Client ID for cache operations. Defaults to 'default' if not specified.",
        ),
        ctx: Context = None,
    ) -> str:
        """Manage workflow session cache for persistence across MCP restarts."""
        try:
            # Handle FieldInfo objects
            if hasattr(client_id, "default"):
                client_id = client_id.default or "default"

            if operation == "restore":
                return _handle_cache_restore_operation(client_id)
            elif operation == "list":
                return _handle_cache_list_operation(client_id)
            elif operation == "stats":
                return _handle_cache_list_operation(client_id)  # Same as list for now
            else:
                return f"❌ **Invalid Operation:** '{operation}' is not supported"

        except Exception as e:
            return f"❌ **Cache Management Error:** {str(e)}"

    @app.tool()
    def workflow_semantic_analysis(
        query: str = Field(
            description="Description of current task, problem, or context to find related past work"
        ),
        client_id: str = Field(
            default="default",
            description="Client ID to search within. Defaults to 'default' if not specified.",
        ),
        max_results: int = Field(
            default=3, description="Maximum number of results to return (1-100)"
        ),
        min_similarity: float = Field(
            default=0.1,
            description="Minimum similarity threshold (0.0-1.0, higher means more similar)",
        ),
        ctx: Context = None,
    ) -> str:
        """Find all relevant past workflow contexts and provide the raw context for agent analysis."""
        try:
            # Handle FieldInfo objects
            if hasattr(client_id, "default"):
                client_id = client_id.default or "default"

            # For now, return placeholder since semantic search is complex
            return f"""📊 **Semantic Analysis Results for:** "{query}"

**Client:** {client_id}
**Parameters:** max_results={max_results}, min_similarity={min_similarity}

⚠️ **Feature Not Available:** Full semantic analysis not implemented in current version.

**Alternative Approach:**
- Use `workflow_cache_management(operation="list")` to see available sessions
- Review session logs manually for relevant patterns
- Consider the current task context when making decisions"""

        except Exception as e:
            return f"❌ **Semantic Analysis Error:** {str(e)}"
