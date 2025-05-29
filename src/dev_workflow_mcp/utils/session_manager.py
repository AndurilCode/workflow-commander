"""Session manager for client-based workflow state persistence."""

import threading
from datetime import UTC, datetime

from ..models.config import S3Config
from ..models.workflow_state import (
    WorkflowItem,
    WorkflowPhase,
    WorkflowState,
    WorkflowStatus,
)
from .s3_client import S3SyncClient

# Global session store with thread-safe access
client_sessions: dict[str, WorkflowState] = {}
session_lock = threading.Lock()

# S3 client for state synchronization
_s3_client: S3SyncClient | None = None


def get_session(client_id: str) -> WorkflowState | None:
    """Get workflow session for a client."""
    with session_lock:
        return client_sessions.get(client_id)


def create_session(client_id: str, task_description: str) -> WorkflowState:
    """Create a new workflow session for a client."""
    with session_lock:
        # Create initial workflow state
        state = WorkflowState(
            client_id=client_id,
            phase=WorkflowPhase.INIT,
            status=WorkflowStatus.READY,
            current_item=task_description,
            items=[WorkflowItem(id=1, description=task_description, status="pending")]
        )
        
        # Store in global sessions
        client_sessions[client_id] = state
        
        return state


def update_session(client_id: str, **kwargs) -> bool:
    """Update an existing session with new field values."""
    with session_lock:
        session = client_sessions.get(client_id)
        if not session:
            return False
        
        # Update fields
        for field, value in kwargs.items():
            if hasattr(session, field):
                setattr(session, field, value)
        
        # Update timestamp
        session.last_updated = datetime.now(UTC)
        
        return True


def delete_session(client_id: str) -> bool:
    """Delete a client session."""
    with session_lock:
        if client_id in client_sessions:
            del client_sessions[client_id]
            return True
        return False


def get_all_sessions() -> dict[str, WorkflowState]:
    """Get all current sessions (returns a copy for safety)."""
    with session_lock:
        return client_sessions.copy()


def export_session_to_markdown(client_id: str) -> str | None:
    """Export a session as markdown string."""
    with session_lock:
        session = client_sessions.get(client_id)
        if not session:
            return None
        
        return session.to_markdown()


def get_or_create_session(client_id: str, task_description: str | None = None) -> WorkflowState:
    """Get existing session or create new one if it doesn't exist."""
    session = get_session(client_id)
    if session is None:
        # Create with default task if none provided
        default_task = task_description or "Default workflow task"
        session = create_session(client_id, default_task)
    
    return session


def add_log_to_session(client_id: str, entry: str) -> bool:
    """Add a log entry to a session."""
    with session_lock:
        session = client_sessions.get(client_id)
        if not session:
            return False
        
        session.add_log_entry(entry)
        return True


def update_session_state(
    client_id: str,
    phase: WorkflowPhase | None = None,
    status: WorkflowStatus | None = None,
    current_item: str | None = None
) -> bool:
    """Update session state fields."""
    updates = {}
    
    if phase is not None:
        updates['phase'] = phase
    if status is not None:
        updates['status'] = status
    # Always update current_item if the parameter was passed (even if None)
    # We need to use a sentinel value to distinguish between "not passed" and "passed as None"
    # For now, we'll always update current_item when this function is called
    updates['current_item'] = current_item
    
    return update_session(client_id, **updates)


def add_item_to_session(client_id: str, description: str) -> bool:
    """Add a new item to session's workflow."""
    with session_lock:
        session = client_sessions.get(client_id)
        if not session:
            return False
        
        # Find next available ID
        next_id = 1
        if session.items:
            next_id = max(item.id for item in session.items) + 1
        
        # Add new item
        new_item = WorkflowItem(id=next_id, description=description, status="pending")
        session.items.append(new_item)
        session.last_updated = datetime.now(UTC)
        
        return True


def mark_item_completed_in_session(client_id: str, item_id: int) -> bool:
    """Mark an item as completed in a session."""
    with session_lock:
        session = client_sessions.get(client_id)
        if not session:
            return False
        
        result = session.mark_item_completed(item_id)
        if result:
            session.last_updated = datetime.now(UTC)
        
        return result


def get_session_stats() -> dict[str, int]:
    """Get statistics about current sessions."""
    with session_lock:
        stats = {
            'total_sessions': len(client_sessions),
            'sessions_by_phase': {},
            'sessions_by_status': {}
        }
        
        for session in client_sessions.values():
            # Count by phase
            phase = session.phase.value
            stats['sessions_by_phase'][phase] = stats['sessions_by_phase'].get(phase, 0) + 1
            
            # Count by status
            status = session.status.value
            stats['sessions_by_status'][status] = stats['sessions_by_status'].get(status, 0) + 1
        
        return stats


def cleanup_completed_sessions(keep_recent_hours: int = 24) -> int:
    """Remove completed sessions older than specified hours."""
    cutoff_time = datetime.now(UTC).timestamp() - (keep_recent_hours * 3600)
    
    with session_lock:
        to_remove = []
        
        for client_id, session in client_sessions.items():
            if (session.status == WorkflowStatus.COMPLETED and 
                session.last_updated.timestamp() < cutoff_time):
                to_remove.append(client_id)
        
        for client_id in to_remove:
            del client_sessions[client_id]
        
        return len(to_remove)


def migrate_session_from_markdown(client_id: str, markdown_content: str) -> bool:
    """Migrate existing markdown workflow state to session."""
    try:
        with session_lock:
            # Parse markdown and create session
            state = WorkflowState.from_markdown(markdown_content, client_id)
            client_sessions[client_id] = state
            return True
    except Exception:
        return False


def initialize_s3_client(config: S3Config) -> None:
    """Initialize the S3 client with configuration."""
    global _s3_client
    _s3_client = S3SyncClient(config)


def sync_session_to_s3(client_id: str, archive: bool = False) -> str | None:
    """Sync a session to S3.
    
    Args:
        client_id: Unique client identifier
        archive: Whether to archive as completed workflow
        
    Returns:
        S3 key if successful, None otherwise
    """
    if not _s3_client:
        return None
    
    session = get_session(client_id)
    if not session:
        return None
    
    # Convert session to dict for S3 storage
    state_dict = {
        "client_id": session.client_id,
        "created_at": session.created_at.isoformat(),
        "last_updated": session.last_updated.isoformat(),
        "phase": session.phase.value,
        "status": session.status.value,
        "current_item": session.current_item,
        "plan": session.plan,
        "items": [
            {"id": item.id, "description": item.description, "status": item.status}
            for item in session.items
        ],
        "log": session.log,
        "archive_log": session.archive_log,
        "markdown_export": session.to_markdown(),
    }
    
    if archive and _s3_client.config.archive_completed:
        return _s3_client.archive_completed_workflow(client_id, state_dict)
    else:
        return _s3_client.sync_workflow_state(client_id, state_dict)


def restore_session_from_s3(client_id: str, s3_key: str) -> bool:
    """Restore a session from S3.
    
    Args:
        client_id: Unique client identifier
        s3_key: S3 key to restore from
        
    Returns:
        True if successful, False otherwise
    """
    if not _s3_client:
        return False
    
    state_data = _s3_client.retrieve_workflow_state(s3_key)
    if not state_data:
        return False
    
    try:
        # Reconstruct WorkflowState from S3 data
        items = [WorkflowItem(**item) for item in state_data.get("items", [])]
        
        state = WorkflowState(
            client_id=client_id,
            phase=WorkflowPhase(state_data.get("phase", "INIT")),
            status=WorkflowStatus(state_data.get("status", "READY")),
            current_item=state_data.get("current_item"),
            plan=state_data.get("plan", ""),
            items=items,
            log=state_data.get("log", ""),
            archive_log=state_data.get("archive_log", ""),
        )
        
        # Update timestamps if available
        if "created_at" in state_data:
            state.created_at = datetime.fromisoformat(state_data["created_at"])
        if "last_updated" in state_data:
            state.last_updated = datetime.fromisoformat(state_data["last_updated"])
        
        # Store in sessions
        with session_lock:
            client_sessions[client_id] = state
        
        return True
        
    except Exception as e:
        import logging
        logging.error(f"Failed to restore session from S3: {e}")
        return False


def reset_session(client_id: str) -> bool:
    """Reset a session to initial state."""
    with session_lock:
        session = client_sessions.get(client_id)
        if not session:
            return False
        
        # Reset to initial state
        session.phase = WorkflowPhase.INIT
        session.status = WorkflowStatus.READY
        session.current_item = None
        session.plan = ""
        session.log = ""
        # Keep archive_log and items
        session.last_updated = datetime.now(UTC)
        
        return True 