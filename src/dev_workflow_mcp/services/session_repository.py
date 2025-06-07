"""Session repository service for core CRUD operations and session management."""

import threading
from datetime import UTC, datetime
from typing import Any, Protocol

from ..models.workflow_state import DynamicWorkflowState
from ..models.yaml_workflow import WorkflowDefinition


class SessionRepositoryProtocol(Protocol):
    """Protocol for session repository operations."""

    def get_session(self, session_id: str) -> DynamicWorkflowState | None:
        """Get a session by ID."""
        ...

    def create_session(
        self,
        client_id: str,
        task_description: str,
        workflow_def: WorkflowDefinition,
        workflow_file: str | None = None,
    ) -> DynamicWorkflowState:
        """Create a new dynamic session."""
        ...

    def update_session(self, session_id: str, **kwargs: Any) -> bool:
        """Update session with provided fields."""
        ...

    def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID."""
        ...

    def get_sessions_by_client(self, client_id: str) -> list[DynamicWorkflowState]:
        """Get all sessions for a client."""
        ...

    def get_all_sessions(self) -> dict[str, DynamicWorkflowState]:
        """Get all sessions."""
        ...

    def get_session_stats(self) -> dict[str, int]:
        """Get session statistics."""
        ...

    def get_session_type(self, session_id: str) -> str | None:
        """Get session type."""
        ...


class SessionRepository:
    """Session repository implementation with thread-safe operations."""

    def __init__(self) -> None:
        self._sessions: dict[str, DynamicWorkflowState] = {}
        self._client_session_registry: dict[str, list[str]] = {}
        self._lock = threading.Lock()
        self._registry_lock = threading.Lock()

    def get_session(self, session_id: str) -> DynamicWorkflowState | None:
        """Get a session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def create_session(
        self,
        client_id: str,
        task_description: str,
        workflow_def: WorkflowDefinition,
        workflow_file: str | None = None,
    ) -> DynamicWorkflowState:
        """Create a new dynamic session."""
        from uuid import uuid4

        session_id = str(uuid4())

        # Prepare dynamic inputs
        inputs = self._prepare_dynamic_inputs(task_description, workflow_def)

        # Create the session
        session = DynamicWorkflowState(
            session_id=session_id,
            client_id=client_id,
            created_at=datetime.now(UTC),
            workflow_name=workflow_def.name,
            workflow_file=workflow_file,
            current_node=workflow_def.workflow.root,
            status="READY",
            inputs=inputs,
            node_outputs={},
            current_item=task_description,
            items=[],
            log=[],
            archive_log=[],
        )

        with self._lock:
            self._sessions[session_id] = session

        # Register session for client
        self._register_session_for_client(client_id, session_id)

        return session

    def update_session(self, session_id: str, **kwargs: Any) -> bool:
        """Update session with provided fields."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False

            # Update fields
            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)

            return True

    def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if not session:
                return False

        # Unregister from client
        self._unregister_session_for_client(session.client_id, session_id)
        return True

    def get_sessions_by_client(self, client_id: str) -> list[DynamicWorkflowState]:
        """Get all sessions for a client."""
        with self._registry_lock:
            session_ids = self._client_session_registry.get(client_id, [])

        sessions = []
        with self._lock:
            for session_id in session_ids:
                if session := self._sessions.get(session_id):
                    sessions.append(session)

        return sessions

    def get_all_sessions(self) -> dict[str, DynamicWorkflowState]:
        """Get all sessions."""
        with self._lock:
            return self._sessions.copy()

    def get_session_stats(self) -> dict[str, int]:
        """Get session statistics."""
        with self._lock:
            sessions = list(self._sessions.values())

        stats = {
            "total_sessions": len(sessions),
            "running_sessions": len([s for s in sessions if s.status == "RUNNING"]),
            "completed_sessions": len([s for s in sessions if s.status == "COMPLETED"]),
            "failed_sessions": len([s for s in sessions if s.status == "FAILED"]),
        }

        # Count by client
        clients = set(s.client_id for s in sessions)
        stats["total_clients"] = len(clients)

        return stats

    def get_session_type(self, session_id: str) -> str | None:
        """Get session type."""
        session = self.get_session(session_id)
        if not session:
            return None

        # Determine type based on workflow name
        if hasattr(session, "workflow_name") and session.workflow_name:
            return "dynamic"
        return "legacy"

    def _prepare_dynamic_inputs(
        self, task_description: str, workflow_def: WorkflowDefinition
    ) -> dict[str, Any]:
        """Prepare dynamic inputs based on workflow definition."""
        inputs: dict[str, Any] = {}

        # Always ensure task_description is included
        inputs["task_description"] = task_description

        # Add other inputs from workflow definition with defaults
        for input_name, input_spec in workflow_def.inputs.items():
            if input_name == "task_description":
                continue  # Already handled

            # Set default values based on type
            input_type = input_spec.type
            if input_type == "boolean":
                inputs[input_name] = (
                    input_spec.default if input_spec.default is not None else False
                )
            elif input_type == "integer":
                inputs[input_name] = (
                    input_spec.default if input_spec.default is not None else 0
                )
            elif input_type == "array":
                inputs[input_name] = (
                    input_spec.default if input_spec.default is not None else []
                )
            else:  # string or others
                inputs[input_name] = (
                    input_spec.default if input_spec.default is not None else ""
                )

        return inputs

    def _register_session_for_client(self, client_id: str, session_id: str) -> None:
        """Register a session for a client."""
        with self._registry_lock:
            if client_id not in self._client_session_registry:
                self._client_session_registry[client_id] = []
            if session_id not in self._client_session_registry[client_id]:
                self._client_session_registry[client_id].append(session_id)

    def _unregister_session_for_client(self, client_id: str, session_id: str) -> None:
        """Unregister a session from a client."""
        with self._registry_lock:
            if client_id in self._client_session_registry:
                try:
                    self._client_session_registry[client_id].remove(session_id)
                    if not self._client_session_registry[client_id]:
                        del self._client_session_registry[client_id]
                except ValueError:
                    pass  # Session not in list
