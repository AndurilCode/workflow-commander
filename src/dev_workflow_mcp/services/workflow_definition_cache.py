"""Workflow definition cache service for workflow definition storage and retrieval."""

import threading
from typing import Protocol

from ..models.yaml_workflow import WorkflowDefinition


class WorkflowDefinitionCacheProtocol(Protocol):
    """Protocol for workflow definition cache operations."""

    def store_workflow_definition_in_cache(
        self, session_id: str, workflow_def: WorkflowDefinition
    ) -> None:
        """Store workflow definition in cache."""
        ...

    def get_workflow_definition_from_cache(
        self, session_id: str
    ) -> WorkflowDefinition | None:
        """Get workflow definition from cache."""
        ...

    def clear_workflow_definition_cache(self, session_id: str) -> None:
        """Clear workflow definition from cache."""
        ...

    def get_session_workflow_def(self, session_id: str) -> WorkflowDefinition | None:
        """Get workflow definition for a session."""
        ...


class WorkflowDefinitionCache:
    """Workflow definition cache implementation for session-based workflow storage."""

    def __init__(self) -> None:
        self._workflow_definitions_cache: dict[str, WorkflowDefinition] = {}
        self._lock = threading.Lock()

    def store_workflow_definition_in_cache(
        self, session_id: str, workflow_def: WorkflowDefinition
    ) -> None:
        """Store workflow definition in cache for session."""
        with self._lock:
            self._workflow_definitions_cache[session_id] = workflow_def

    def get_workflow_definition_from_cache(
        self, session_id: str
    ) -> WorkflowDefinition | None:
        """Get workflow definition from cache for session."""
        with self._lock:
            return self._workflow_definitions_cache.get(session_id)

    def clear_workflow_definition_cache(self, session_id: str) -> None:
        """Clear workflow definition from cache for session."""
        with self._lock:
            self._workflow_definitions_cache.pop(session_id, None)

    def get_session_workflow_def(self, session_id: str) -> WorkflowDefinition | None:
        """Get workflow definition for a session (alias for get_workflow_definition_from_cache)."""
        return self.get_workflow_definition_from_cache(session_id)

    def clear_all_cached_definitions(self) -> int:
        """Clear all cached workflow definitions and return count."""
        with self._lock:
            count = len(self._workflow_definitions_cache)
            self._workflow_definitions_cache.clear()
            return count

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics."""
        with self._lock:
            return {
                "total_cached_definitions": len(self._workflow_definitions_cache),
                "cached_session_ids": len(self._workflow_definitions_cache.keys()),
            }

    def list_cached_session_ids(self) -> list[str]:
        """List all session IDs with cached workflow definitions."""
        with self._lock:
            return list(self._workflow_definitions_cache.keys())
