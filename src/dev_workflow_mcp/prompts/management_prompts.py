"""Management prompts for workflow completion, iteration, and error handling."""

from fastmcp import Context, FastMCP
from pydantic import Field

from ..models.workflow_state import WorkflowPhase, WorkflowStatus
from ..utils.session_manager import (
    add_log_to_session,
    export_session_to_markdown,
    get_session,
    mark_item_completed_in_session,
    reset_session,
    sync_session_to_s3,
    update_session_state,
)


def register_management_prompts(mcp: FastMCP):
    """Register all management-related prompts."""

    @mcp.tool()
    def complete_workflow_guidance(task_description: str, ctx: Context) -> str:
        """Guide the agent through workflow completion with mandatory execution steps."""
        # Update session to completed status
        client_id = ctx.client_id if ctx else "default"
        session = get_session(client_id)
        
        if session:
            update_session_state(client_id, status=WorkflowStatus.COMPLETED)
            add_log_to_session(client_id, f"✅ COMPLETED: {task_description}")
            
            # Mark current item as completed if it matches task description
            for item in session.items:
                if item.description == task_description and item.status == "pending":
                    mark_item_completed_in_session(client_id, item.id)
                    break
        
        # Get updated state to return
        updated_state = export_session_to_markdown(client_id)
        
        return f"""🎉 WORKFLOW TASK COMPLETED

**Task:** {task_description}

**✅ STATE UPDATED AUTOMATICALLY:**
- Status → COMPLETED
- Item marked as completed
- Log entry added

**📋 CURRENT WORKFLOW STATE:**
```markdown
{updated_state}
```

**🔄 NEXT STEPS:**

✅ **IF MORE ITEMS EXIST:**
Call: `iterate_next_item_guidance`

✅ **IF ALL ITEMS COMPLETE:**
Call: `finalize_workflow_guidance`

**💡 OPTIONAL:**
Call: `changelog_update_guidance` if project changelog needs updating

🎯 **Task completion automated - check workflow state above for next actions!**
"""

    @mcp.tool()
    def iterate_next_item_guidance(ctx: Context) -> str:
        """Guide the agent to process the next workflow item with mandatory execution steps."""
        # Find next pending item and update session
        client_id = ctx.client_id if ctx else "default"
        session = get_session(client_id)
        
        next_item = None
        if session:
            next_item = session.get_next_pending_item()
            if next_item:
                update_session_state(
                    client_id=client_id,
                    phase=WorkflowPhase.ANALYZE,
                    status=WorkflowStatus.READY,
                    current_item=next_item.description
                )
                add_log_to_session(client_id, f"🔄 STARTING NEXT ITEM: {next_item.description}")
        
        # Get updated state to return
        updated_state = export_session_to_markdown(client_id)
        
        if next_item:
            return f"""🔄 PROCESSING NEXT WORKFLOW ITEM

**Next Item:** {next_item.description}

**✅ STATE UPDATED AUTOMATICALLY:**
- Phase → ANALYZE
- Status → READY  
- CurrentItem → {next_item.description}
- Log archived and cleared for new item

**📋 CURRENT WORKFLOW STATE:**
```markdown
{updated_state}
```

**🔄 NEXT STEP:**
Call: `analyze_phase_guidance`
Parameters: task_description="{next_item.description}"

🎯 **Ready to analyze next item - state updated automatically!**
"""
        else:
            return f"""🏁 NO MORE ITEMS TO PROCESS

**✅ STATE CURRENT:**
```markdown
{updated_state}
```

**🔄 NEXT STEP:**
Call: `finalize_workflow_guidance`

🎯 **All items completed - ready to finalize workflow!**
"""

    @mcp.tool()
    def finalize_workflow_guidance(ctx: Context) -> str:
        """Guide the agent to finalize the entire workflow with mandatory execution steps."""
        # Reset session to initial state
        client_id = ctx.client_id if ctx else "default"
        
        # Add final summary to log before archiving
        session = get_session(client_id)
        if session:
            completed_items = [item for item in session.items if item.status == "completed"]
            add_log_to_session(
                client_id, 
                f"🏁 WORKFLOW FINALIZED - {len(completed_items)} items completed successfully"
            )
        
        # Get final state before reset
        updated_state = export_session_to_markdown(client_id)
        
        # Sync to S3 if enabled (archive mode)
        s3_key = sync_session_to_s3(client_id, archive=True)
        if s3_key:
            add_log_to_session(client_id, f"📤 Workflow archived to S3: {s3_key}")
        
        # Reset session state
        reset_session(client_id)
        
        # Build S3 sync message
        s3_msg = ""
        if s3_key:
            s3_msg = f"\n- Workflow archived to S3: `{s3_key}`"
        
        return f"""🏁 WORKFLOW FINALIZED

**✅ STATE UPDATED AUTOMATICALLY:**
- Phase → INIT
- Status → READY
- CurrentItem → null
- Final summary logged and archived{s3_msg}

**📋 FINAL WORKFLOW STATE:**
```markdown
{updated_state}
```

**🎉 WORKFLOW COMPLETE!**
- All items processed
- State reset for future workflows
- Session data preserved for reference

💫 **No further actions needed - workflow cycle complete!**
"""

    @mcp.tool()
    def error_recovery_guidance(
        task_description: str,
        ctx: Context,
        error_details: str = Field(
            description="Description of the error that occurred"
        ),  
    ) -> str:
        """Guide the agent through error recovery with mandatory execution steps."""
        # Log error in session and update status
        client_id = ctx.client_id if ctx and ctx.client_id is not None else "default"
        add_log_to_session(client_id, f"🚨 ERROR: {error_details}")
        update_session_state(client_id, status=WorkflowStatus.ERROR)
        
        # Get updated state to return
        updated_state = export_session_to_markdown(client_id)
        
        return f"""🚨 ERROR RECOVERY MODE

**Task:** {task_description}
**Error:** {error_details}

**✅ STATE UPDATED AUTOMATICALLY:**
- Status → ERROR
- Error logged with timestamp

**📋 CURRENT WORKFLOW STATE:**
```markdown
{updated_state}
```

**🔧 RECOVERY OPTIONS:**

**✅ FOR SIMPLE FIXES:**
Fix the issue, then call: `construct_phase_guidance`
Parameters: task_description="{task_description}"

**🔄 FOR COMPLEX ISSUES:**
Return to planning: `blueprint_phase_guidance`  
Parameters: task_description="{task_description}", requirements_summary="Error occurred: {error_details}"

**⚠️ FOR CRITICAL ERRORS:**
Escalate: `escalate_to_user_guidance`
Parameters: task_description="{task_description}", error_details="{error_details}"

🎯 **Error logged automatically - choose recovery path above!**
"""

    @mcp.tool()
    def fix_validation_issues_guidance(
        task_description: str,
        ctx: Context,
        issues: str = Field(description="Description of validation issues found"),
    ) -> str:
        """Guide the agent to fix validation issues with mandatory execution steps."""
        # Log validation issues in session
        client_id = ctx.client_id if ctx and ctx.client_id is not None else "default"
        add_log_to_session(client_id, f"🔧 VALIDATION ISSUES: {issues}")
        update_session_state(client_id, status=WorkflowStatus.ERROR)
        
        # Get updated state to return
        updated_state = export_session_to_markdown(client_id)
        
        return f"""🔧 FIXING VALIDATION ISSUES

**Task:** {task_description}
**Issues:** {issues}

**✅ STATE UPDATED AUTOMATICALLY:**
- Status → ERROR
- Issues logged with timestamp

**📋 CURRENT WORKFLOW STATE:**
```markdown
{updated_state}
```

**🔧 REQUIRED ACTIONS:**
1. Fix each validation issue systematically
2. Test fixes incrementally  
3. Log progress as you work

**🔄 AFTER FIXES COMPLETE:**
Call: `validate_phase_guidance`
Parameters: task_description="{task_description}"

**🚨 IF ISSUES PERSIST:**
Call: `error_recovery_guidance`
Parameters: task_description="{task_description}", error_details="Persistent validation issues: {issues}"

🎯 **Issues logged automatically - proceed with systematic fixes!**
"""

    @mcp.tool()
    def escalate_to_user_guidance(
        task_description: str,
        ctx: Context,
        error_details: str = Field(
            description="Critical error details requiring user intervention"
        ),
    ) -> str:
        """Guide the agent to escalate critical issues to the user with mandatory execution steps."""
        # Update session to error status and log
        client_id = ctx.client_id if ctx and ctx.client_id is not None else "default"
        update_session_state(client_id, status=WorkflowStatus.ERROR)
        add_log_to_session(client_id, f"⚠️ CRITICAL ERROR - ESCALATED: {error_details}")
        
        # Get updated state to return
        updated_state = export_session_to_markdown(client_id)
        
        return f"""⚠️ ESCALATING TO USER

**Task:** {task_description}  
**Critical Error:** {error_details}

**✅ STATE UPDATED AUTOMATICALLY:**
- Status → ERROR
- Critical error logged and escalated

**📋 CURRENT WORKFLOW STATE:**
```markdown
{updated_state}
```

**📋 USER SUMMARY:**
- **What was attempted:** {task_description}
- **What went wrong:** {error_details}
- **Current state:** See workflow state above
- **Action needed:** User guidance on how to proceed

**🔄 AFTER USER PROVIDES GUIDANCE:**
Follow user instructions and call appropriate workflow prompt based on their guidance.

**✅ TO RETRY AFTER USER FIX:**
Call: `construct_phase_guidance`
Parameters: task_description="{task_description}"

⚠️ **Critical error escalated automatically - waiting for user guidance!**
"""

    @mcp.tool()
    def changelog_update_guidance(
        task_description: str,
        ctx: Context,
        project_config_path: str = Field(
            default="project_config.md",
            description="Path to project configuration file",
        ),        
    ) -> str:
        """Guide the agent to update the project changelog with mandatory execution steps."""
        # Log changelog update in session
        client_id = ctx.client_id if ctx and ctx.client_id is not None else "default"
        add_log_to_session(client_id, f"📝 Updating project changelog for: {task_description}")
        
        # Get current state to return
        updated_state = export_session_to_markdown(client_id)
        
        return f"""📝 UPDATING PROJECT CHANGELOG

**Task:** {task_description}

**✅ STATE LOGGED:**
- Changelog update initiated
- Progress tracked in workflow state

**📋 CURRENT WORKFLOW STATE:**
```markdown
{updated_state}
```

**📝 REQUIRED ACTIONS:**
1. Read {project_config_path} to locate ## Changelog section
2. Create concise changelog entry (one sentence, past tense)
3. Insert as first item after ## Changelog heading
4. Maintain existing format
5. Save the updated file

**📋 CHANGELOG ENTRY FORMAT:**
```
- [Date] <One sentence summary of completed work>
```

**✅ WHEN COMPLETE:**
Return to calling workflow prompt or continue with workflow as appropriate.

🎯 **Changelog update logged - proceed with file modifications!**
"""
