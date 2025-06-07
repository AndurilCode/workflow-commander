"""Session manager for session-ID-based workflow state persistence."""

import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..models.workflow_state import (
    DynamicWorkflowState,
    WorkflowItem,
)
from ..models.yaml_workflow import WorkflowDefinition
from ..utils.yaml_loader import WorkflowLoader

# Global session store with thread-safe access - NOW KEYED BY SESSION_ID
sessions: dict[str, DynamicWorkflowState] = {}
session_lock = threading.Lock()

# Client to session mapping for multi-session support
client_session_registry: dict[str, list[str]] = {}
registry_lock = threading.Lock()

# Global workflow definition cache for dynamically created workflows
workflow_definitions_cache: dict[str, WorkflowDefinition] = {}
workflow_cache_lock = threading.Lock()

# Global server configuration for auto-sync functionality
_server_config = None
_server_config_lock = threading.Lock()

# Global cache manager for workflow state persistence
_cache_manager = None
_cache_manager_lock = threading.Lock()


def _get_server_config_from_service():
    """Get server configuration from the configuration service.
    
    Returns:
        ServerConfig or None: Legacy server config instance or None if not available
    """
    try:
        from ..services.dependency_injection import get_service
        from ..services.config_service import ConfigurationService
        
        # Try to get from dependency injection first
        config_service = get_service(ConfigurationService)
        if config_service:
            return config_service.to_legacy_server_config()
    except Exception:
        pass
    
    try:
        from ..services.config_service import get_configuration_service
        
        # Fallback to global configuration service
        config_service = get_configuration_service()
        return config_service.to_legacy_server_config()
    except Exception:
        pass
    
    return None


def _get_effective_server_config():
    """Get effective server configuration using modern service or legacy fallback.
    
    Returns:
        ServerConfig or None: Configuration instance
    """
    # Try modern configuration service first
    service_config = _get_server_config_from_service()
    if service_config:
        return service_config
    
    # Fallback to legacy global variable
    global _server_config
    with _server_config_lock:
        return _server_config


def set_server_config(server_config) -> None:
    """Set the server configuration for auto-sync functionality.

    Args:
        server_config: ServerConfig instance with session storage settings
        
    Note:
        This function is maintained for backward compatibility but is deprecated.
        New code should use the configuration service instead.
    """
    global _server_config, _cache_manager
    with _server_config_lock:
        _server_config = server_config

        # Initialize cache manager if cache mode is enabled
        if server_config and server_config.enable_cache_mode:
            _initialize_cache_manager(server_config)


def _initialize_cache_manager(server_config) -> bool:
    """Initialize the cache manager with server configuration.

    Args:
        server_config: ServerConfig instance

    Returns:
        bool: True if initialization successful
    """
    global _cache_manager

    with _cache_manager_lock:
        if _cache_manager is not None:
            return True  # Already initialized

        try:
            from .cache_manager import WorkflowCacheManager

            # Ensure cache directory exists
            if not server_config.ensure_cache_dir():
                return False

            _cache_manager = WorkflowCacheManager(
                db_path=str(server_config.cache_dir),
                collection_name=server_config.cache_collection_name,
                embedding_model=server_config.cache_embedding_model,
                max_results=server_config.cache_max_results,
            )

            return True

        except Exception as e:
            print(f"Warning: Failed to initialize cache manager: {e}")
            return False


def _should_initialize_cache_from_environment() -> bool:
    """Check if cache manager should be initialized from environment indicators.

    This function detects when cache mode should be enabled based on:
    1. Cache directory existence (indicates cache was configured)
    2. MCP configuration context hints

    Returns:
        bool: True if cache initialization should be attempted
    """
    try:
        import os
        from pathlib import Path

        # Method 1: Check for cache directory existence
        cache_paths = [
            ".workflow-commander/cache",  # Default relative path
            Path.cwd() / ".workflow-commander" / "cache",  # Current directory
            Path("~/.workflow-commander/cache").expanduser(),  # User home
        ]

        for cache_path in cache_paths:
            if Path(cache_path).exists() and Path(cache_path).is_dir():
                return True

        # Method 2: Check for MCP server arguments in environment
        # This catches cases where cache was configured but directory doesn't exist yet
        command_line = " ".join(os.environ.get("MCP_COMMAND_LINE", "").split())
        if "--enable-cache-mode" in command_line:
            return True

        # Method 3: Check if we're in a repository that likely has cache configured
        workflow_commander_dir = Path(".workflow-commander")
        return workflow_commander_dir.exists() and workflow_commander_dir.is_dir()

    except Exception:
        return False


def _reinitialize_cache_from_environment() -> bool:
    """Reinitialize cache manager from environment detection.

    This function attempts to recreate cache manager configuration
    when module reimport has reset global variables.

    Returns:
        bool: True if reinitialization successful
    """
    global _cache_manager, _server_config

    try:
        import os
        from pathlib import Path

        from ..config import ServerConfig

        # Determine appropriate cache configuration
        cache_path = None
        embedding_model = "all-MiniLM-L6-v2"  # Safe default
        max_results = 50

        # Try to find existing cache directory
        cache_paths = [
            ".workflow-commander/cache",
            Path.cwd() / ".workflow-commander" / "cache",
            Path("~/.workflow-commander/cache").expanduser(),
        ]

        for path in cache_paths:
            if Path(path).exists() and Path(path).is_dir():
                cache_path = str(path)
                break

        # If no existing cache dir, use default location
        if not cache_path:
            cache_path = ".workflow-commander/cache"

        # Try to extract configuration from environment if available
        command_line = os.environ.get("MCP_COMMAND_LINE", "")
        if "--cache-embedding-model" in command_line:
            # Extract embedding model from command line
            parts = command_line.split()
            try:
                model_idx = parts.index("--cache-embedding-model") + 1
                if model_idx < len(parts):
                    embedding_model = parts[model_idx]
            except (ValueError, IndexError):
                pass  # Use default

        if "--cache-max-results" in command_line:
            # Extract max results from command line
            parts = command_line.split()
            try:
                results_idx = parts.index("--cache-max-results") + 1
                if results_idx < len(parts):
                    max_results = int(parts[results_idx])
            except (ValueError, IndexError):
                pass  # Use default

        # Create minimal config for cache initialization
        temp_config = ServerConfig(
            repository_path=".",
            enable_cache_mode=True,
            cache_db_path=cache_path,
            cache_embedding_model=embedding_model,
            cache_max_results=max_results,
        )

        # Initialize cache manager with detected configuration
        success = _initialize_cache_manager(temp_config)

        if success:
            # Store the config for future reference (helps with subsequent calls)
            _server_config = temp_config

        return success

    except Exception as e:
        # Minimal logging to avoid noise, but track the issue
        print(f"Warning: Failed to reinitialize cache from environment: {e}")
        return False


def _is_test_environment() -> bool:
    """Check if we're running in a test environment.

    Returns:
        True if running in tests, False otherwise
    """
    import os
    import sys

    # Check for pytest in sys.modules
    if "pytest" in sys.modules:
        return True

    # Check for common test environment variables
    test_indicators = [
        "PYTEST_CURRENT_TEST",
        "CI",
        "GITHUB_ACTIONS",
        "_called_from_test",
    ]

    for indicator in test_indicators:
        if os.environ.get(indicator):
            return True

    # Check for test in command line arguments
    return bool(any("test" in arg.lower() for arg in sys.argv))


def get_cache_manager():
    """Get the global cache manager instance.

    Returns:
        WorkflowCacheManager or None if not available
    """
    global _cache_manager, _server_config

    # Skip cache initialization entirely in test environments
    if _is_test_environment():
        return None

    with _cache_manager_lock:
        # Check if cache manager is uninitialized due to module reimport
        # but we can detect cache mode should be enabled from environment
        if _cache_manager is None and _should_initialize_cache_from_environment():
            print("Debug: Attempting cache manager reinitialization from environment")
            success = _reinitialize_cache_from_environment()
            print(
                f"Debug: Cache manager reinitialization {'succeeded' if success else 'failed'}"
            )

        if _cache_manager is None:
            print("Debug: Cache manager unavailable - skipping cache operations")
        else:
            print(
                f"Debug: Cache manager available - is_available: {_cache_manager.is_available()}"
            )

        return _cache_manager


def _restore_workflow_definition(
    session: DynamicWorkflowState, workflows_dir: str = ".workflow-commander/workflows"
) -> None:
    """Helper function to restore workflow definition for a session.

    Args:
        session: The restored session state
        workflows_dir: Directory containing workflow YAML files
    """
    try:
        print(
            f"DEBUG: _restore_workflow_definition called for session {session.session_id[:8]}..."
        )

        if not session.workflow_name:
            print(f"DEBUG: No workflow name for session {session.session_id[:8]}...")
            return

        print(
            f"DEBUG: Restoring workflow '{session.workflow_name}' for session {session.session_id[:8]}..."
        )

        # Check if workflow definition is already cached
        cached_def = get_workflow_definition_from_cache(session.session_id)
        if cached_def:
            print(
                f"DEBUG: Workflow definition already cached for session {session.session_id[:8]}..."
            )
            return  # Already available

        print(f"DEBUG: Loading workflow definition from {workflows_dir}...")

        # Load workflow definition using WorkflowLoader
        from ..utils.yaml_loader import WorkflowLoader

        loader = WorkflowLoader(workflows_dir)
        workflow_def = loader.get_workflow_by_name(session.workflow_name)

        if workflow_def:
            print(
                f"DEBUG: Successfully loaded workflow '{workflow_def.name}', storing in cache..."
            )
            # Store in workflow definition cache
            store_workflow_definition_in_cache(session.session_id, workflow_def)
            print(
                f"DEBUG: Workflow definition cached for session {session.session_id[:8]}..."
            )
        else:
            print(
                f"DEBUG: Failed to load workflow '{session.workflow_name}' for session {session.session_id[:8]}..."
            )

    except Exception as e:
        # Gracefully handle any workflow loading failures
        # Session restoration should succeed even if workflow definition fails
        print(f"DEBUG: Exception in _restore_workflow_definition: {e}")
        pass


def restore_sessions_from_cache(client_id: str | None = None) -> int:
    """Restore workflow sessions from cache on startup.

    Args:
        client_id: Optional client ID to restore sessions for specific client only

    Returns:
        Number of sessions restored from cache
    """
    cache_manager = get_cache_manager()
    if not cache_manager or not cache_manager.is_available():
        return 0

    try:
        restored_count = 0
        print(f"DEBUG: restore_sessions_from_cache called with client_id='{client_id}'")

        if client_id:
            print(f"DEBUG: Restoring sessions for specific client: {client_id}")
            # Restore sessions for specific client
            client_session_metadata = cache_manager.get_all_sessions_for_client(
                client_id
            )
            print(
                f"DEBUG: Found {len(client_session_metadata)} sessions for client {client_id}"
            )
            for metadata in client_session_metadata:
                session_id = metadata.session_id
                restored_state = cache_manager.retrieve_workflow_state(session_id)
                if restored_state:
                    with session_lock:
                        sessions[session_id] = restored_state
                        _register_session_for_client(client_id, session_id)

                    # Automatically restore workflow definition
                    _restore_workflow_definition(restored_state)
                    restored_count += 1
        else:
            print(
                "DEBUG: Restoring all sessions from all clients (no specific client_id)"
            )
            # Restore all sessions from all clients when no specific client_id provided
            try:
                # Use cache manager to get all sessions across all clients
                all_session_metadata = cache_manager.get_all_sessions()
                print(
                    f"DEBUG: Found {len(all_session_metadata)} total sessions across all clients"
                )

                for metadata in all_session_metadata:
                    session_id = metadata.session_id
                    metadata_client_id = metadata.client_id

                    # Attempt to restore each session
                    restored_state = cache_manager.retrieve_workflow_state(session_id)
                    if restored_state:
                        with session_lock:
                            sessions[session_id] = restored_state
                            _register_session_for_client(metadata_client_id, session_id)

                        # Automatically restore workflow definition
                        _restore_workflow_definition(restored_state)
                        restored_count += 1

            except AttributeError:
                # Fallback: If cache manager doesn't have get_all_sessions method,
                # we'll use the existing per-client restoration approach for known clients
                # This approach is safer and doesn't require knowledge of all client IDs
                restored_count = 0  # No restoration if we can't get all sessions

        return restored_count

    except Exception:
        # Non-blocking: don't break startup on cache restoration failures
        return 0


def auto_restore_sessions_on_startup() -> int:
    """Automatically restore all workflow sessions from cache during server startup.

    This function is designed to be called during MCP server initialization
    to restore any existing workflow sessions from the cache. It operates
    in a completely non-blocking manner and will not prevent server startup
    even if cache restoration fails.

    Returns:
        Number of sessions restored from cache (0 if cache unavailable or disabled)
    """
    # Check if we're in a test environment - skip auto-restoration during tests
    if _is_test_environment():
        return 0

    cache_manager = get_cache_manager()
    if not cache_manager or not cache_manager.is_available():
        return 0

    try:
        restored_count = 0

        # Get all available sessions from cache
        try:
            # Use cache manager to get all sessions across all clients
            all_session_metadata = cache_manager.get_all_sessions()

            for metadata in all_session_metadata:
                session_id = metadata.session_id
                client_id = metadata.client_id

                # Attempt to restore each session
                restored_state = cache_manager.retrieve_workflow_state(session_id)
                if restored_state:
                    with session_lock:
                        sessions[session_id] = restored_state
                        _register_session_for_client(client_id, session_id)

                    # Automatically restore workflow definition
                    _restore_workflow_definition(restored_state)
                    restored_count += 1

        except AttributeError:
            # Fallback: If cache manager doesn't have get_all_sessions method,
            # we'll use the existing per-client restoration approach for known clients
            # This ensures backward compatibility with different cache manager versions

            # For now, we'll try to restore for the default client
            # This approach is safer and doesn't require knowledge of all client IDs
            restored_count = restore_sessions_from_cache("default")

        return restored_count

    except Exception as e:
        # Completely non-blocking: log error but don't prevent server startup
        # In production, you might want to use proper logging instead of print
        print(f"Info: Automatic cache restoration skipped due to error: {e}")
        return 0


def list_cached_sessions(client_id: str | None = None) -> list[dict]:
    """List available sessions in cache for restoration.

    Args:
        client_id: Optional client ID to filter sessions

    Returns:
        List of session metadata dictionaries
    """
    cache_manager = get_cache_manager()
    if not cache_manager or not cache_manager.is_available():
        return []

    try:
        if client_id:
            session_metadata_list = cache_manager.get_all_sessions_for_client(client_id)
            sessions_info = []

            for metadata in session_metadata_list:
                sessions_info.append(
                    {
                        "session_id": metadata.session_id,
                        "workflow_name": metadata.workflow_name,
                        "status": metadata.status,
                        "current_node": metadata.current_node,
                        "created_at": metadata.created_at.isoformat(),
                        "last_updated": metadata.last_updated.isoformat(),
                        "task_description": metadata.current_item
                        if metadata.current_item
                        else "No description",
                    }
                )

            return sessions_info
        else:
            # Get cache stats to show available sessions
            cache_stats = cache_manager.get_cache_stats()
            if cache_stats:
                return [
                    {
                        "total_cached_sessions": cache_stats.total_entries,
                        "active_sessions": cache_stats.active_sessions,
                        "completed_sessions": cache_stats.completed_sessions,
                        "oldest_entry": cache_stats.oldest_entry.isoformat()
                        if cache_stats.oldest_entry
                        else None,
                        "newest_entry": cache_stats.newest_entry.isoformat()
                        if cache_stats.newest_entry
                        else None,
                    }
                ]

        return []

    except Exception:
        return []


def _generate_unique_session_filename(
    session_id: str, format_ext: str, sessions_dir: Path
) -> str:
    """Generate a unique session filename with timestamp and counter.

    Args:
        session_id: Session identifier
        format_ext: File extension (e.g., 'json', 'md')
        sessions_dir: Directory where session files are stored

    Returns:
        str: Unique filename in format: {session_id}_{timestamp}_{counter}.{ext}
    """
    # Clean session_id for filesystem safety
    safe_session_id = re.sub(r"[^\w\-_]", "_", session_id)

    # Generate ISO timestamp for filename (replace : with - for filesystem compatibility)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")

    # Find existing files with same session_id and timestamp to generate counter
    pattern = f"{safe_session_id}_{timestamp}_*.{format_ext}"
    existing_files = list(sessions_dir.glob(pattern))

    # Generate next counter
    counter = len(existing_files) + 1

    return f"{safe_session_id}_{timestamp}_{counter:03d}.{format_ext}"


def _sync_session_to_file(
    session_id: str, session: DynamicWorkflowState | None = None
) -> bool:
    """Automatically sync session to filesystem when enabled.

    Args:
        session_id: Session ID for session lookup
        session: Optional session object to avoid lock re-acquisition

    Returns:
        bool: True if sync succeeded or was skipped, False on error
    """
    config = _get_effective_server_config()
    
    if not config or not config.enable_local_state_file:
        return True  # Skip if disabled or no config

    try:
        # Ensure sessions directory exists
        if not config.ensure_sessions_dir():
            return False

        # Get session content - avoid lock re-acquisition if session provided
        if session is None:
            session = get_session(session_id)
        if not session:
            return False

        # Determine file format and content
        format_ext = config.local_state_file_format.lower()

        # Generate or use existing unique filename for this session
        if not session.session_filename:
            # Generate new unique filename and store it in session
            unique_filename = _generate_unique_session_filename(
                session_id, format_ext, config.sessions_dir
            )
            session.session_filename = unique_filename

        session_file = config.sessions_dir / session.session_filename

        if config.local_state_file_format == "JSON":
            content = session.to_json()
        else:
            content = session.to_markdown()

        if not content:
            return False

        # Atomic write operation
        temp_file = session_file.with_suffix(f".{format_ext}.tmp")
        temp_file.write_text(content, encoding="utf-8")
        temp_file.rename(session_file)

        return True

    except Exception:
        # Non-blocking: don't break workflow execution on sync failures
        return False


def _sync_session_to_cache(
    session_id: str, session: DynamicWorkflowState | None = None
) -> bool:
    """Sync session to cache when enabled.

    Args:
        session_id: Session ID for session lookup
        session: Optional session object to avoid lock re-acquisition

    Returns:
        bool: True if sync succeeded or was skipped, False on error
    """
    cache_manager = get_cache_manager()
    if not cache_manager or not cache_manager.is_available():
        # DEBUG: Log cache availability for troubleshooting
        print(
            f"Debug: Cache sync skipped for session {session_id[:8]} - cache_manager: {cache_manager is not None}, available: {cache_manager.is_available() if cache_manager else False}"
        )
        return True  # Skip if cache disabled or unavailable

    try:
        # Get session if not provided
        if session is None:
            session = get_session(session_id)
        if not session:
            print(
                f"Debug: Cache sync failed for session {session_id[:8]} - session not found"
            )
            return False

        # Store in cache
        result = cache_manager.store_workflow_state(session)
        print(
            f"Debug: Cache sync for session {session_id[:8]} - success: {result.success}"
        )
        return result.success

    except Exception as e:
        # Non-blocking: don't break workflow execution on cache failures
        print(f"Warning: Failed to sync session to cache: {e}")
        return False


def sync_session(session_id: str) -> bool:
    """Explicitly sync a session to filesystem and cache after manual modifications.

    Use this function after directly modifying session fields outside of
    session_manager functions to ensure changes are persisted.

    Args:
        session_id: The session identifier

    Returns:
        bool: True if sync succeeded or was skipped, False on error
    """
    print(f"Debug: Explicit sync requested for session {session_id[:8]}")
    file_sync = _sync_session_to_file(session_id)
    cache_sync = _sync_session_to_cache(session_id)

    print(f"Debug: Explicit sync results - file: {file_sync}, cache: {cache_sync}")

    # Return True if at least one sync method succeeded
    return file_sync or cache_sync


def force_cache_sync_session(session_id: str) -> dict[str, any]:
    """Force cache sync for a specific session with detailed diagnostics.

    Args:
        session_id: The session identifier

    Returns:
        dict: Detailed sync results and diagnostics
    """
    results = {
        "session_id": session_id,
        "session_found": False,
        "cache_manager_available": False,
        "cache_sync_attempted": False,
        "cache_sync_success": False,
        "error": None,
    }

    try:
        # Check session existence
        session = get_session(session_id)
        results["session_found"] = session is not None

        if not session:
            results["error"] = "Session not found in memory"
            return results

        # Check cache manager
        cache_manager = get_cache_manager()
        results["cache_manager_available"] = cache_manager is not None and (
            cache_manager.is_available() if cache_manager else False
        )

        if not cache_manager or not cache_manager.is_available():
            results["error"] = "Cache manager not available"
            return results

        # Attempt cache sync
        results["cache_sync_attempted"] = True
        result = cache_manager.store_workflow_state(session)
        results["cache_sync_success"] = result.success

        if not result.success:
            results["error"] = result.error_message

        return results

    except Exception as e:
        results["error"] = str(e)
        return results


def get_session(session_id: str) -> DynamicWorkflowState | None:
    """Get workflow session by session ID."""
    with session_lock:
        return sessions.get(session_id)


def get_sessions_by_client(client_id: str) -> list[DynamicWorkflowState]:
    """Get all sessions for a specific client."""
    with registry_lock:
        session_ids = client_session_registry.get(client_id, [])

    with session_lock:
        return [sessions[sid] for sid in session_ids if sid in sessions]


def _register_session_for_client(client_id: str, session_id: str) -> None:
    """Register a session ID for a client (internal function)."""
    with registry_lock:
        if client_id not in client_session_registry:
            client_session_registry[client_id] = []
        if session_id not in client_session_registry[client_id]:
            client_session_registry[client_id].append(session_id)


def _unregister_session_for_client(client_id: str, session_id: str) -> None:
    """Unregister a session ID for a client (internal function)."""
    with registry_lock:
        if client_id in client_session_registry:
            if session_id in client_session_registry[client_id]:
                client_session_registry[client_id].remove(session_id)
            # Clean up empty client entries
            if not client_session_registry[client_id]:
                del client_session_registry[client_id]


def _prepare_dynamic_inputs(
    task_description: str, workflow_def: WorkflowDefinition
) -> dict[str, Any]:
    """Prepare and validate workflow inputs dynamically.

    Args:
        task_description: The task description to be processed
        workflow_def: Workflow definition containing input specifications

    Returns:
        dict[str, Any]: Prepared and validated inputs
    """
    provided_inputs = {}

    # Step 1: Smart task description mapping
    # Check for common task description input patterns
    task_input_name = None
    for input_name in ["task_description", "task", "main_task"]:
        if input_name in workflow_def.inputs:
            task_input_name = input_name
            break

    if task_input_name:
        provided_inputs[task_input_name] = task_description

    # Step 2: Set defaults for all other inputs dynamically
    for input_name, input_def in workflow_def.inputs.items():
        if input_name not in provided_inputs:
            if input_def.default is not None:
                # Use defined default value
                provided_inputs[input_name] = input_def.default
            elif input_def.required:
                # Generate type-based defaults for required inputs without defaults
                if input_def.type == "string":
                    provided_inputs[input_name] = ""
                elif input_def.type == "boolean":
                    provided_inputs[input_name] = False
                elif input_def.type == "number":
                    provided_inputs[input_name] = 0
                else:
                    # For unknown types, use None
                    provided_inputs[input_name] = None

    # Step 3: Validate all inputs using workflow definition
    try:
        validated_inputs = workflow_def.validate_inputs(provided_inputs)
        return validated_inputs
    except ValueError:
        # If validation fails, provide minimal fallback
        return {"task_description": task_description}


def create_dynamic_session(
    client_id: str,
    task_description: str,
    workflow_def: WorkflowDefinition,
    workflow_file: str | None = None,
) -> DynamicWorkflowState:
    """Create a new dynamic workflow session.

    Args:
        client_id: The client identifier
        task_description: Description of the task to be processed
        workflow_def: The workflow definition to use
        workflow_file: Optional path to the workflow YAML file

    Returns:
        DynamicWorkflowState: The created session state
    """
    with session_lock:
        # Validate and process workflow inputs dynamically
        inputs = _prepare_dynamic_inputs(task_description, workflow_def)

        # Create initial dynamic workflow state (session_id auto-generated by model)
        state = DynamicWorkflowState(
            client_id=client_id,
            workflow_name=workflow_def.name,
            workflow_file=workflow_file,
            current_node=workflow_def.workflow.root,
            status="READY",
            inputs=inputs,
            current_item=task_description,
            items=[WorkflowItem(id=1, description=task_description, status="pending")],
        )

        # Add initial log entry
        state.add_log_entry(f"🚀 DYNAMIC WORKFLOW INITIALIZED: {workflow_def.name}")
        state.add_log_entry(f"📍 Starting at root node: {workflow_def.workflow.root}")

        # Store in global sessions using session_id as key
        sessions[state.session_id] = state

        # Register session for client
        _register_session_for_client(client_id, state.session_id)

        # Auto-sync to filesystem and cache if enabled (pass session to avoid lock re-acquisition)
        _sync_session_to_file(state.session_id, state)
        _sync_session_to_cache(state.session_id, state)

        return state


def update_session(session_id: str, **kwargs) -> bool:
    """Update an existing session with new field values."""
    with session_lock:
        session = sessions.get(session_id)
        if not session:
            return False

        # Update fields
        for field, value in kwargs.items():
            if hasattr(session, field):
                setattr(session, field, value)

        # Update timestamp
        session.last_updated = datetime.now(UTC)

        # Auto-sync to filesystem and cache if enabled (pass session to avoid lock re-acquisition)
        _sync_session_to_file(session_id, session)
        cache_sync_result = _sync_session_to_cache(session_id, session)

        # Force cache sync for completed workflows
        if kwargs.get("status") in ["COMPLETED", "FINISHED"] and not cache_sync_result:
            print(
                f"Debug: Workflow completion detected for {session_id[:8]}, forcing cache sync"
            )
            # Try cache sync again after brief delay to allow for cache initialization
            import time

            time.sleep(0.1)
            cache_sync_result = _sync_session_to_cache(session_id, session)
            print(f"Debug: Forced cache sync result: {cache_sync_result}")

        return True


def update_dynamic_session_node(
    session_id: str,
    new_node: str,
    workflow_def: WorkflowDefinition,
    status: str | None = None,
    outputs: dict | None = None,
) -> bool:
    """Update a dynamic session's current node with validation.

    Args:
        session_id: The session identifier
        new_node: The node to transition to
        workflow_def: The workflow definition for validation
        status: Optional new status
        outputs: Optional outputs from the previous node

    Returns:
        bool: True if successful
    """
    with session_lock:
        session = sessions.get(session_id)
        if not session or not isinstance(session, DynamicWorkflowState):
            return False

        # Complete current node with outputs if provided
        if outputs:
            session.complete_current_node(outputs)
        else:
            # Even if no outputs provided, mark node as completed with basic tracking
            # This ensures node_outputs has an entry for the completed node
            basic_outputs = {
                "goal_achieved": True,
                "completion_method": "automatic_transition",
                "completed_without_detailed_outputs": True,
            }
            session.complete_current_node(basic_outputs)

        # Transition to new node
        success = session.transition_to_node(new_node, workflow_def)

        if success and status:
            session.status = status

        # Auto-sync to filesystem and cache if enabled (pass session to avoid lock re-acquisition)
        if success:
            _sync_session_to_file(session_id, session)
            _sync_session_to_cache(session_id, session)

        return success


def delete_session(session_id: str) -> bool:
    """Delete a session."""
    with session_lock:
        session = sessions.get(session_id)
        if not session:
            return False

        client_id = session.client_id

        # Remove from sessions
        del sessions[session_id]

        # Unregister from client
        _unregister_session_for_client(client_id, session_id)

        return True


def get_all_sessions() -> dict[str, DynamicWorkflowState]:
    """Get all current sessions (returns a copy for safety)."""
    with session_lock:
        return sessions.copy()


def export_session_to_markdown(
    session_id: str, workflow_def: WorkflowDefinition | None = None
) -> str | None:
    """Export a session as markdown string."""
    with session_lock:
        session = sessions.get(session_id)
        if not session or not isinstance(session, DynamicWorkflowState):
            return None

        return session.to_markdown(workflow_def)


def export_session_to_json(session_id: str) -> str | None:
    """Export a session as JSON string."""
    with session_lock:
        session = sessions.get(session_id)
        if not session or not isinstance(session, DynamicWorkflowState):
            return None

        return session.to_json()


def export_session(
    session_id: str, format: str = "MD", workflow_def: WorkflowDefinition | None = None
) -> str | None:
    """Export a session in the specified format.

    Args:
        session_id: Session ID for session lookup.
        format: Export format - "MD" for markdown or "JSON" for JSON.
        workflow_def: Optional workflow definition for dynamic sessions

    Returns:
        Formatted string representation of session state or None if session doesn't exist.
    """
    format_upper = format.upper()

    if format_upper == "MD":
        return export_session_to_markdown(session_id, workflow_def)
    elif format_upper == "JSON":
        return export_session_to_json(session_id)
    else:
        # Default to markdown for unsupported formats
        return export_session_to_markdown(session_id, workflow_def)


def get_or_create_dynamic_session(
    client_id: str,
    task_description: str,
    workflow_name: str | None = None,
    workflows_dir: str = ".workflow-commander/workflows",
) -> DynamicWorkflowState | None:
    """Get existing session or create a new dynamic one if it doesn't exist.

    Args:
        client_id: The client identifier
        task_description: Description of the task
        workflow_name: Optional specific workflow name to use
        workflows_dir: Directory containing workflow definitions

    Returns:
        DynamicWorkflowState | None: The session or None if no workflows found
    """
    # NOTE: This function is now primarily for backward compatibility
    # The new approach should use create_dynamic_session directly with explicit session management

    # Check if client has any existing sessions
    existing_sessions = get_sessions_by_client(client_id)
    if existing_sessions:
        # Return the most recent session for backwards compatibility
        return max(existing_sessions, key=lambda s: s.last_updated)

    # No existing sessions, try to create one
    try:
        loader = WorkflowLoader(workflows_dir)
        workflows = loader.discover_workflows()

        if not workflows:
            return None

        # Use specified workflow or first available
        selected_workflow = None
        if workflow_name and workflow_name in workflows:
            selected_workflow = workflows[workflow_name]
        elif workflows:
            selected_workflow = next(iter(workflows.values()))

        if selected_workflow:
            return create_dynamic_session(
                client_id, task_description, selected_workflow
            )

    except Exception:
        pass  # Fallback gracefully

    return None


def add_log_to_session(session_id: str, entry: str) -> bool:
    """Add log entry to a session."""
    with session_lock:
        session = sessions.get(session_id)
        if not session:
            return False

        session.add_log_entry(entry)
        session.last_updated = datetime.now(UTC)

        # Auto-sync to filesystem and cache if enabled (pass session to avoid lock re-acquisition)
        _sync_session_to_file(session_id, session)
        _sync_session_to_cache(session_id, session)

        return True


def update_dynamic_session_status(
    session_id: str,
    status: str | None = None,
    current_item: str | None = None,
) -> bool:
    """Update dynamic session state fields."""
    updates = {}

    if status is not None:
        updates["status"] = status
    if current_item is not None:
        updates["current_item"] = current_item

    return update_session(session_id, **updates)


def add_item_to_session(session_id: str, description: str) -> bool:
    """Add an item to a session."""
    with session_lock:
        session = sessions.get(session_id)
        if not session:
            return False

        # Get next ID
        next_id = max([item.id for item in session.items], default=0) + 1

        # Add new item
        new_item = WorkflowItem(id=next_id, description=description, status="pending")
        session.items.append(new_item)
        session.last_updated = datetime.now(UTC)

        # Auto-sync to filesystem and cache if enabled (pass session to avoid lock re-acquisition)
        _sync_session_to_file(session_id, session)
        _sync_session_to_cache(session_id, session)

        return True


def mark_item_completed_in_session(session_id: str, item_id: int) -> bool:
    """Mark an item as completed in a session."""
    with session_lock:
        session = sessions.get(session_id)
        if not session:
            return False

        result = session.mark_item_completed(item_id)
        if result:
            session.last_updated = datetime.now(UTC)
            # Auto-sync to filesystem and cache if enabled (pass session to avoid lock re-acquisition)
            _sync_session_to_file(session_id, session)
            _sync_session_to_cache(session_id, session)

        return result


def get_session_type(session_id: str) -> str | None:
    """Get the type of session.

    Args:
        session_id: The session identifier

    Returns:
        str | None: "dynamic" or None if session doesn't exist
    """
    with session_lock:
        session = sessions.get(session_id)
        if not session:
            return None

        if isinstance(session, DynamicWorkflowState):
            return "dynamic"
        else:
            return None


def get_session_stats() -> dict[str, int]:
    """Get statistics about current sessions."""
    with session_lock:
        stats = {
            "total_sessions": len(sessions),
            "dynamic_sessions": 0,
            "sessions_by_status": {},
        }

        for session in sessions.values():
            if isinstance(session, DynamicWorkflowState):
                stats["dynamic_sessions"] += 1
                # For dynamic sessions, track by status
                status = session.status
                stats["sessions_by_status"][status] = (
                    stats["sessions_by_status"].get(status, 0) + 1
                )

        return stats


def _archive_session_file(session: DynamicWorkflowState) -> bool:
    """Archive a completed session file by adding completion timestamp to filename.

    Args:
        session: The session to archive

    Returns:
        bool: True if archiving succeeded, False otherwise
    """
    config = _get_effective_server_config()
    
    if not config or not config.enable_local_state_file:
        return True  # Skip if disabled

    try:
        if not session.session_filename:
            return True  # No file to archive

        sessions_dir = config.sessions_dir
        current_file = sessions_dir / session.session_filename

        if not current_file.exists():
            return True  # File doesn't exist, nothing to archive

        # Generate archived filename with completion timestamp
        completion_timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
        base_name = session.session_filename.rsplit(".", 1)[0]  # Remove extension
        extension = session.session_filename.rsplit(".", 1)[1]  # Get extension

        archived_filename = f"{base_name}_COMPLETED_{completion_timestamp}.{extension}"
        archived_file = sessions_dir / archived_filename

        # Move current file to archived location
        current_file.rename(archived_file)

        return True

    except Exception:
        # Non-blocking: don't break workflow execution on archive failures
        return False


def cleanup_completed_sessions(
    keep_recent_hours: int = 24, archive_before_cleanup: bool = True
) -> int:
    """Clean up old completed sessions with optional archiving.

    Args:
        keep_recent_hours: Keep sessions modified within this many hours
        archive_before_cleanup: Whether to archive session files before cleanup

    Returns:
        Number of sessions cleaned up
    """
    cutoff_time = datetime.now(UTC).timestamp() - (keep_recent_hours * 3600)
    cleaned_count = 0

    with session_lock:
        sessions_to_remove = []

        for session_id, session in sessions.items():
            # Check if session is completed and old enough
            session_time = session.last_updated.timestamp()

            is_completed = False
            if isinstance(session, DynamicWorkflowState):
                # For dynamic sessions, check if at a terminal node or status indicates completion
                is_completed = session.status.upper() in [
                    "COMPLETED",
                    "ERROR",
                    "FINISHED",
                ]

            if is_completed and session_time < cutoff_time:
                # Archive the session file before removing from memory
                if archive_before_cleanup:
                    _archive_session_file(session)

                sessions_to_remove.append(session_id)

        # Remove the sessions from memory and registry
        for session_id in sessions_to_remove:
            session = sessions[session_id]
            client_id = session.client_id

            del sessions[session_id]
            _unregister_session_for_client(client_id, session_id)
            cleaned_count += 1

    return cleaned_count


def get_dynamic_session_workflow_def(session_id: str) -> WorkflowDefinition | None:
    """Get the workflow definition for a dynamic session.

    Args:
        session_id: The session identifier

    Returns:
        WorkflowDefinition | None: The workflow definition or None if not available
    """
    with session_lock:
        session = sessions.get(session_id)
        if not session or not isinstance(session, DynamicWorkflowState):
            return None

        # First check the cache for dynamically created workflows
        cached_def = get_workflow_definition_from_cache(session_id)
        if cached_def:
            return cached_def

        # Try to load the workflow definition from filesystem
        try:
            if session.workflow_file:
                # Load from specific file
                loader = WorkflowLoader()
                return loader.load_workflow(Path(session.workflow_file))
            else:
                # Load from workflows directory by name
                loader = WorkflowLoader()
                workflows = loader.load_all_workflows()
                return workflows.get(session.workflow_name)
        except Exception:
            return None


def store_workflow_definition_in_cache(
    session_id: str, workflow_def: WorkflowDefinition
) -> None:
    """Store a workflow definition in the cache for a session.

    Args:
        session_id: The session identifier
        workflow_def: The workflow definition to store
    """
    with workflow_cache_lock:
        workflow_definitions_cache[session_id] = workflow_def


def get_workflow_definition_from_cache(session_id: str) -> WorkflowDefinition | None:
    """Get a workflow definition from the cache for a session.

    Args:
        session_id: The session identifier

    Returns:
        WorkflowDefinition | None: The cached workflow definition or None
    """
    with workflow_cache_lock:
        return workflow_definitions_cache.get(session_id)


def clear_workflow_definition_cache(session_id: str) -> None:
    """Clear the workflow definition cache for a session.

    Args:
        session_id: The session identifier
    """
    with workflow_cache_lock:
        workflow_definitions_cache.pop(session_id, None)


def detect_session_conflict(client_id: str) -> dict[str, any] | None:
    """Detect if there are existing sessions for a client.

    NOTE: This function has been disabled to fix multi-chat environment conflicts.
    In environments like Cursor with multiple chat windows, client_id-based conflict
    detection creates false positives. Each chat should operate independently.

    DEPRECATED: Client-based conflict detection is disabled.
    Use session-specific operations with explicit session_id instead.

    Args:
        client_id: The client identifier (preserved for backward compatibility)

    Returns:
        None: Always returns None - no conflicts detected

    MIGRATION: Code using this function should transition to:
    - Direct session_id management for resuming specific sessions
    - Independent session creation per conversation/chat
    - Optional: Context-aware session discovery for smart resumption
    """
    # DISABLED: Always return None to prevent false conflicts in multi-chat environments
    # This fixes the core issue where multiple chat windows in Cursor share the same client_id
    # but should operate independently without conflict detection.
    return None

    # ORIGINAL LOGIC (preserved for reference, now commented out):
    # existing_sessions = get_sessions_by_client(client_id)
    # if not existing_sessions:
    #     return None
    # [... rest of original logic would be here ...]


def get_session_summary(session_id: str) -> str:
    """Get a human-readable summary of a session state.

    Args:
        session_id: The session identifier

    Returns:
        str: Formatted summary of the session, or "Session not found" if none exists
    """
    session = get_session(session_id)
    if not session:
        return "Session not found"

    return (
        f"**{session.workflow_name}** (dynamic)\n"
        f"• Session ID: {session.session_id}\n"
        f"• Current: {session.current_node}\n"
        f"• Status: {session.status}\n"
        f"• Task: {session.current_item}\n"
        f"• Last Updated: {session.last_updated.isoformat()}"
    )


def clear_session_completely(session_id: str) -> dict[str, any]:
    """Completely clear a session and all associated data.

    This function provides atomic cleanup of all session-related data including
    the main session, workflow cache, and any other associated state.

    Args:
        session_id: The session identifier

    Returns:
        dict: Cleanup results with the following keys:
        - success: bool - Whether cleanup was successful
        - session_cleared: bool - Whether main session was removed
        - cache_cleared: bool - Whether workflow cache was cleared
        - session_type: str | None - Type of session that was cleared
        - error: str | None - Error message if cleanup failed
    """
    results = {
        "success": False,
        "session_cleared": False,
        "cache_cleared": False,
        "session_type": None,
        "error": None,
    }

    try:
        # Get session info before clearing
        session = get_session(session_id)
        if session:
            results["session_type"] = "dynamic"

        # Clear main session with thread safety
        success = delete_session(session_id)
        results["session_cleared"] = success

        # Clear workflow definition cache
        clear_workflow_definition_cache(session_id)
        results["cache_cleared"] = True

        # Mark as successful if session was cleared
        results["success"] = success

        return results

    except Exception as e:
        results["error"] = str(e)
        return results


def clear_all_client_sessions(client_id: str) -> dict[str, any]:
    """Clear all sessions for a specific client.

    Args:
        client_id: The client identifier

    Returns:
        dict: Cleanup results with the following keys:
        - success: bool - Whether cleanup was successful overall
        - sessions_cleared: int - Number of sessions cleared
        - failed_sessions: list - List of sessions that failed to clear
        - previous_session_type: str - Type of sessions that were cleared
        - error: str | None - Error message if cleanup failed
    """
    results = {
        "success": False,
        "sessions_cleared": 0,
        "failed_sessions": [],
        "previous_session_type": "dynamic",
        "error": None,
    }

    try:
        # Get all sessions for the client
        client_sessions = get_sessions_by_client(client_id)

        if not client_sessions:
            results["success"] = True
            return results

        # Clear each session
        for session in client_sessions:
            session_result = clear_session_completely(session.session_id)
            if session_result["success"]:
                results["sessions_cleared"] += 1
            else:
                results["failed_sessions"].append(
                    {
                        "session_id": session.session_id,
                        "error": session_result.get("error", "Unknown error"),
                    }
                )

        # Mark as successful if all sessions were cleared
        results["success"] = len(results["failed_sessions"]) == 0

        return results

    except Exception as e:
        results["error"] = str(e)
        return results
