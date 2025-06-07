"""Session lifecycle manager for cleanup, archival, and conflict detection."""

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from ..models.workflow_state import DynamicWorkflowState


class SessionLifecycleManagerProtocol(Protocol):
    """Protocol for session lifecycle operations."""

    def cleanup_completed_sessions(
        self, keep_recent_hours: int = 24, archive_before_cleanup: bool = True
    ) -> int:
        """Clean up completed sessions."""
        ...

    def archive_session_file(self, session: DynamicWorkflowState) -> bool:
        """Archive a session file."""
        ...

    def clear_session_completely(self, session_id: str) -> dict[str, Any]:
        """Clear a session completely."""
        ...

    def clear_all_client_sessions(self, client_id: str) -> dict[str, Any]:
        """Clear all sessions for a client."""
        ...

    def detect_session_conflict(self, client_id: str) -> dict[str, Any] | None:
        """Detect session conflicts for a client."""
        ...

    def get_session_summary(self, session_id: str) -> str:
        """Get session summary."""
        ...


class SessionLifecycleManager:
    """Session lifecycle manager implementation for cleanup and archival."""

    def __init__(
        self,
        session_repository: Any,
        session_sync_service: Any,
        cache_manager: Any = None,
    ) -> None:
        self._session_repository = session_repository
        self._session_sync_service = session_sync_service
        self._cache_manager = cache_manager
        self._lock = threading.Lock()

    def cleanup_completed_sessions(
        self, keep_recent_hours: int = 24, archive_before_cleanup: bool = True
    ) -> int:
        """Clean up completed sessions older than specified hours."""
        try:
            cutoff_time = datetime.now(UTC) - timedelta(hours=keep_recent_hours)
            sessions_to_cleanup = []

            # Find sessions to clean up
            all_sessions = self._session_repository.get_all_sessions()
            for _session_id, session in all_sessions.items():
                # Normalize session.created_at to UTC for comparison
                session_created_at = session.created_at
                if session_created_at.tzinfo is None:
                    # Make naive datetime timezone-aware by assuming UTC
                    session_created_at = session_created_at.replace(tzinfo=UTC)
                
                if (
                    session.status in ["COMPLETED", "FAILED"]
                    and session_created_at < cutoff_time
                ):
                    sessions_to_cleanup.append(session)

            cleanup_count = 0
            for session in sessions_to_cleanup:
                try:
                    # Archive first if requested
                    if archive_before_cleanup:
                        self.archive_session_file(session)

                    # Remove from repository
                    if self._session_repository.delete_session(session.session_id):
                        cleanup_count += 1

                    # Remove from cache if available
                    if self._cache_manager:
                        try:
                            self._cache_manager.delete(session.session_id)
                        except Exception as e:
                            print(
                                f"Warning: Failed to delete session {session.session_id} from cache: {e}"
                            )

                except Exception as e:
                    print(
                        f"Warning: Failed to cleanup session {session.session_id}: {e}"
                    )
                    continue

            return cleanup_count

        except Exception as e:
            print(f"Warning: Session cleanup failed: {e}")
            return 0

    def archive_session_file(self, session: DynamicWorkflowState) -> bool:
        """Archive a session file by moving it to archive directory with status suffix."""
        try:
            server_config = self._get_effective_server_config()
            if not server_config or not server_config.enable_local_state_file:
                return True  # Not enabled, consider success

            # Check if session has a filename to archive
            if not session.session_filename:
                return True  # No file to archive, consider success

            # Find the original session file
            sessions_dir = Path(server_config.get_sessions_dir())
            original_file = sessions_dir / session.session_filename

            if not original_file.exists():
                return True  # No file to archive, consider success

            # Generate archive filename by adding status to original filename
            # Example: test_client_2025-06-04T10-30-00_001.json -> test_client_2025-06-04T10-30-00_001_COMPLETED_20250604_143000.json
            completion_time = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            name_parts = original_file.stem.split(".")
            base_name = name_parts[0]
            archive_filename = f"{base_name}_{session.status.upper()}_{completion_time}.json"
            archive_path = sessions_dir / archive_filename

            # Move the original file to the archived name (in same directory, not archive subdirectory)
            original_file.rename(archive_path)

            return True

        except Exception as e:
            print(f"Warning: Failed to archive session {session.session_id}: {e}")
            return False

    def clear_session_completely(self, session_id: str) -> dict[str, Any]:
        """Clear a session completely from all storage."""
        result: dict[str, Any] = {
            "session_id": session_id,
            "success": False,
            "details": {},
            "message": "",
        }

        try:
            # Get session for archival
            session = self._session_repository.get_session(session_id)
            if not session:
                result["message"] = f"Session {session_id} not found"
                return result

            # Archive before clearing
            archive_success = self.archive_session_file(session)
            result["details"]["archived"] = archive_success

            # Remove from repository
            repo_success = self._session_repository.delete_session(session_id)
            result["details"]["removed_from_repository"] = repo_success

            # Remove from cache
            cache_success = True
            if self._cache_manager:
                try:
                    self._cache_manager.delete(session_id)
                    result["details"]["removed_from_cache"] = True
                except Exception as e:
                    result["details"]["removed_from_cache"] = False
                    result["details"]["cache_error"] = str(e)
                    cache_success = False
            else:
                result["details"]["removed_from_cache"] = "not_enabled"

            # Clear workflow definition cache
            try:
                from .workflow_definition_cache import WorkflowDefinitionCache

                workflow_cache = WorkflowDefinitionCache()
                workflow_cache.clear_workflow_definition_cache(session_id)
                result["details"]["cleared_workflow_cache"] = True
            except Exception:
                result["details"]["cleared_workflow_cache"] = False

            result["success"] = repo_success and cache_success
            result["message"] = (
                "Session cleared successfully"
                if result["success"]
                else "Partial clearing completed"
            )

        except Exception as e:
            result["message"] = f"Error clearing session: {e}"
            result["details"]["error"] = str(e)

        return result

    def clear_all_client_sessions(self, client_id: str) -> dict[str, Any]:
        """Clear all sessions for a client."""
        result: dict[str, Any] = {
            "client_id": client_id,
            "success": False,
            "sessions_processed": 0,
            "sessions_cleared": 0,
            "errors": [],
            "message": "",
        }

        try:
            # Get all sessions for client
            sessions = self._session_repository.get_sessions_by_client(client_id)
            result["sessions_processed"] = len(sessions)

            if not sessions:
                result["success"] = True
                result["message"] = f"No sessions found for client {client_id}"
                return result

            # Clear each session
            for session in sessions:
                try:
                    clear_result = self.clear_session_completely(session.session_id)
                    if clear_result["success"]:
                        result["sessions_cleared"] += 1
                    else:
                        result["errors"].append(
                            {
                                "session_id": session.session_id,
                                "error": clear_result["message"],
                            }
                        )
                except Exception as e:
                    result["errors"].append(
                        {"session_id": session.session_id, "error": str(e)}
                    )

            result["success"] = (
                result["sessions_cleared"] == result["sessions_processed"]
            )
            result["message"] = (
                f"Cleared {result['sessions_cleared']}/{result['sessions_processed']} sessions for client {client_id}"
            )

        except Exception as e:
            result["message"] = f"Error clearing client sessions: {e}"
            result["errors"].append({"error": str(e)})

        return result

    def detect_session_conflict(self, client_id: str) -> dict[str, Any] | None:
        """Detect session conflicts for a client."""
        try:
            sessions = self._session_repository.get_sessions_by_client(client_id)

            # Check for multiple running sessions
            running_sessions = [s for s in sessions if s.status == "RUNNING"]

            if len(running_sessions) > 1:
                return {
                    "conflict_type": "multiple_running_sessions",
                    "client_id": client_id,
                    "running_sessions": [
                        {
                            "session_id": s.session_id,
                            "workflow_name": s.workflow_name,
                            "created_at": s.created_at.isoformat(),
                            "current_node": s.current_node,
                        }
                        for s in running_sessions
                    ],
                    "recommendation": "Consider completing or canceling one of the running sessions",
                }

            # Check for stale sessions (running for more than 24 hours)
            stale_cutoff = datetime.now(UTC) - timedelta(hours=24)
            stale_sessions = [
                s for s in running_sessions if s.created_at < stale_cutoff
            ]

            if stale_sessions:
                return {
                    "conflict_type": "stale_running_sessions",
                    "client_id": client_id,
                    "stale_sessions": [
                        {
                            "session_id": s.session_id,
                            "workflow_name": s.workflow_name,
                            "created_at": s.created_at.isoformat(),
                            "current_node": s.current_node,
                            "hours_running": (
                                datetime.now(UTC) - s.created_at
                            ).total_seconds()
                            / 3600,
                        }
                        for s in stale_sessions
                    ],
                    "recommendation": "Consider checking and potentially cleaning up stale sessions",
                }

            return None  # No conflicts detected

        except Exception as e:
            print(
                f"Warning: Failed to detect session conflicts for client {client_id}: {e}"
            )
            return None

    def get_session_summary(self, session_id: str) -> str:
        """Get a concise summary of session state."""
        session = self._session_repository.get_session(session_id)
        if not session:
            return "Session not found"

        # Calculate session duration
        duration = datetime.now(UTC) - session.created_at
        duration_str = f"{int(duration.total_seconds() / 3600)}h {int((duration.total_seconds() % 3600) / 60)}m"

        # Count completed items
        completed_items = len(
            [
                item
                for item in session.items
                if getattr(item, "completed", False)
                or getattr(item, "status", "") == "completed"
            ]
        )
        total_items = len(session.items)

        summary_parts = [
            f"Session: {session_id[:8]}...",
            f"Client: {session.client_id}",
            f"Task: {session.current_item or 'Unknown'}",
            f"Workflow: {session.workflow_name or 'Unknown'}",
            f"Status: {session.status}",
            f"Current: {session.current_node}",
            f"Duration: {duration_str}",
            f"Items: {completed_items}/{total_items} completed",
            f"Log entries: {len(session.log)}",
        ]

        return " | ".join(summary_parts)

    def _get_effective_server_config(self) -> Any:
        """Get effective server configuration."""
        try:
            from ..services.config_service import ConfigurationService
            from ..services.dependency_injection import get_service

            config_service = get_service(ConfigurationService)
            if config_service:
                return config_service.to_legacy_server_config()
        except Exception:
            pass

        try:
            from ..services.config_service import get_configuration_service

            config_service = get_configuration_service()
            return config_service.to_legacy_server_config()
        except Exception:
            pass

        return None
