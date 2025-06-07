"""Session sync service for file and cache persistence operations."""

import json
import threading
from pathlib import Path
from typing import Any, Protocol

from ..models.workflow_state import DynamicWorkflowState
from ..utils.yaml_loader import WorkflowLoader


class SessionSyncServiceProtocol(Protocol):
    """Protocol for session sync operations."""

    def sync_session_to_file(
        self, session_id: str, session: DynamicWorkflowState | None = None
    ) -> bool:
        """Sync session to file storage."""
        ...

    def sync_session_to_cache(
        self, session_id: str, session: DynamicWorkflowState | None = None
    ) -> bool:
        """Sync session to cache storage."""
        ...

    def sync_session(self, session_id: str) -> bool:
        """Sync session to both file and cache."""
        ...

    def force_cache_sync_session(self, session_id: str) -> dict[str, Any]:
        """Force sync session to cache with detailed results."""
        ...

    def restore_sessions_from_cache(self, client_id: str | None = None) -> int:
        """Restore sessions from cache storage."""
        ...

    def auto_restore_sessions_on_startup(self) -> int:
        """Auto-restore sessions on startup."""
        ...

    def list_cached_sessions(
        self, client_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List cached sessions."""
        ...


class SessionSyncService:
    """Session sync service implementation for file and cache persistence."""

    def __init__(self, session_repository: Any, cache_manager: Any = None) -> None:
        self._session_repository = session_repository
        self._cache_manager = cache_manager
        self._lock = threading.Lock()

    def sync_session_to_file(
        self, session_id: str, session: DynamicWorkflowState | None = None
    ) -> bool:
        """Sync session to file storage."""
        if session is None:
            session = self._session_repository.get_session(session_id)

        if not session:
            return False

        try:
            # Get server config to determine file settings
            server_config = self._get_effective_server_config()
            if not server_config or not server_config.enable_local_state_file:
                return True  # Not enabled, consider success

            # Ensure sessions directory exists
            sessions_dir = Path(server_config.get_sessions_dir())
            sessions_dir.mkdir(parents=True, exist_ok=True)

            # Generate unique filename
            filename = self._generate_unique_session_filename(
                session_id, server_config.local_state_file_format, sessions_dir
            )

            file_path = sessions_dir / filename

            # Prepare session data
            session_data = session.model_dump()

            # Write to file based on format
            if server_config.local_state_file_format.upper() == "JSON":
                with open(file_path, "w") as f:
                    json.dump(session_data, f, indent=2, default=str)
            else:  # Markdown
                markdown_content = self._session_to_markdown(session)
                with open(file_path, "w") as f:
                    f.write(markdown_content)

            return True

        except Exception as e:
            print(f"Warning: Failed to sync session {session_id} to file: {e}")
            return False

    def sync_session_to_cache(
        self, session_id: str, session: DynamicWorkflowState | None = None
    ) -> bool:
        """Sync session to cache storage."""
        if not self._cache_manager:
            return True  # No cache manager, consider success

        if session is None:
            session = self._session_repository.get_session(session_id)

        if not session:
            return False

        try:
            # Store session in cache
            context_text = self._generate_session_context_text(session)
            metadata = {
                "session_id": session_id,
                "client_id": session.client_id,
                "workflow_name": session.workflow_name or "",
                "status": session.status,
                "created_at": session.created_at.isoformat(),
            }

            self._cache_manager.store(
                session_id=session_id,
                context_text=context_text,
                metadata=metadata,
            )

            return True

        except Exception as e:
            print(f"Warning: Failed to sync session {session_id} to cache: {e}")
            return False

    def sync_session(self, session_id: str) -> bool:
        """Sync session to both file and cache."""
        session = self._session_repository.get_session(session_id)
        if not session:
            return False

        file_success = self.sync_session_to_file(session_id, session)
        cache_success = self.sync_session_to_cache(session_id, session)

        return file_success and cache_success

    def force_cache_sync_session(self, session_id: str) -> dict[str, Any]:
        """Force sync session to cache with detailed results."""
        result: dict[str, Any] = {
            "session_id": session_id,
            "success": False,
            "message": "",
            "cache_enabled": False,
        }

        if not self._cache_manager:
            result["message"] = "Cache manager not available"
            return result

        result["cache_enabled"] = True

        session = self._session_repository.get_session(session_id)
        if not session:
            result["message"] = f"Session {session_id} not found"
            return result

        try:
            success = self.sync_session_to_cache(session_id, session)
            result["success"] = success
            result["message"] = (
                "Successfully synced to cache" if success else "Failed to sync to cache"
            )

        except Exception as e:
            result["message"] = f"Error syncing to cache: {e}"

        return result

    def restore_sessions_from_cache(self, client_id: str | None = None) -> int:
        """Restore sessions from cache storage."""
        if not self._cache_manager:
            return 0

        try:
            # Get all sessions from cache
            cached_sessions = self._cache_manager.get_all_sessions_for_client(client_id)

            restored_count = 0
            for session_data in cached_sessions:
                try:
                    # Restore workflow definition
                    session = DynamicWorkflowState(**session_data)
                    self._restore_workflow_definition(session)

                    # Store in repository
                    with self._session_repository._lock:
                        self._session_repository._sessions[session.session_id] = session

                    # Register for client
                    self._session_repository._register_session_for_client(
                        session.client_id, session.session_id
                    )

                    restored_count += 1

                except Exception as e:
                    print(
                        f"Warning: Failed to restore session {session_data.get('session_id', 'unknown')}: {e}"
                    )
                    continue

            return restored_count

        except Exception as e:
            print(f"Warning: Failed to restore sessions from cache: {e}")
            return 0

    def auto_restore_sessions_on_startup(self) -> int:
        """Auto-restore sessions on startup."""
        server_config = self._get_effective_server_config()
        if not server_config or not server_config.enable_cache_mode:
            return 0

        return self.restore_sessions_from_cache()

    def list_cached_sessions(
        self, client_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List cached sessions."""
        if not self._cache_manager:
            return []

        try:
            sessions = self._cache_manager.get_all_sessions_for_client(client_id)
            return sessions if sessions is not None else []
        except Exception as e:
            print(f"Warning: Failed to list cached sessions: {e}")
            return []

    def _generate_unique_session_filename(
        self, session_id: str, format_ext: str, sessions_dir: Path
    ) -> str:
        """Generate unique session filename."""
        import re
        from datetime import datetime

        # Clean session_id for filename
        clean_session_id = re.sub(r'[<>:"/\\|?*]', "_", session_id)[:50]

        # Get current timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Determine extension
        ext = "json" if format_ext.upper() == "JSON" else "md"

        # Find next available counter
        counter = 1
        while True:
            filename = f"{clean_session_id}_{timestamp}_{counter:03d}.{ext}"
            if not (sessions_dir / filename).exists():
                return filename
            counter += 1

    def _session_to_markdown(self, session: DynamicWorkflowState) -> str:
        """Convert session to markdown format."""
        export_session_to_markdown = None
        try:
            from ..prompts.formatting import export_session_to_markdown  # type: ignore
        except ImportError:
            # Fallback if export function not available
            pass

        # Try to get workflow definition for proper formatting
        workflow_def = None
        try:
            from .workflow_definition_cache import WorkflowDefinitionCache

            cache_service = WorkflowDefinitionCache()
            workflow_def = cache_service.get_workflow_definition_from_cache(
                session.session_id
            )
        except Exception:
            pass

        if workflow_def and export_session_to_markdown is not None:
            result = export_session_to_markdown(session.session_id, workflow_def)
            return result if result is not None else self._fallback_markdown(session)
        else:
            return self._fallback_markdown(session)

    def _fallback_markdown(self, session: DynamicWorkflowState) -> str:
        """Generate fallback markdown format."""
        lines = [
            f"# Session: {session.session_id}",
            "",
            f"**Client ID**: {session.client_id}",
            f"**Workflow**: {session.workflow_name or 'Unknown'}",
            f"**Status**: {session.status}",
            f"**Created**: {session.created_at}",
            f"**Current Node**: {session.current_node}",
            "",
            "## Inputs",
            "```json",
            json.dumps(session.inputs, indent=2),
            "```",
            "",
            "## Log",
        ]

        for entry in session.log:
            lines.append(f"- {entry}")

        return "\n".join(lines)

    def _generate_session_context_text(self, session: DynamicWorkflowState) -> str:
        """Generate context text for cache storage."""
        context_parts = [
            f"Session: {session.session_id}",
            f"Client: {session.client_id}",
            f"Workflow: {session.workflow_name or 'Unknown'}",
            f"Status: {session.status}",
            f"Current Node: {session.current_node}",
        ]

        # Add inputs
        if session.inputs:
            context_parts.append("Inputs:")
            for key, value in session.inputs.items():
                context_parts.append(f"  {key}: {value}")

        # Add log entries
        if session.log:
            context_parts.append("Log:")
            for entry in session.log[-5:]:  # Last 5 entries
                context_parts.append(f"  {entry}")

        return "\n".join(context_parts)

    def _restore_workflow_definition(
        self,
        session: DynamicWorkflowState,
        workflows_dir: str = ".workflow-commander/workflows",
    ) -> None:
        """Restore workflow definition for a session."""
        if not session.workflow_file:
            return

        try:
            workflow_path = Path(workflows_dir) / session.workflow_file
            if workflow_path.exists():
                loader = WorkflowLoader()
                workflow_def = loader.load_workflow(str(workflow_path))

                # Store in cache for future use
                if workflow_def is not None:
                    try:
                        from .workflow_definition_cache import WorkflowDefinitionCache

                        cache_service = WorkflowDefinitionCache()
                        cache_service.store_workflow_definition_in_cache(
                            session.session_id, workflow_def
                        )
                    except Exception:
                        pass

        except Exception as e:
            print(
                f"Warning: Failed to restore workflow definition for session {session.session_id}: {e}"
            )

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
