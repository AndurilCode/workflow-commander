"""Configuration helper functions for migration support."""

from pathlib import Path

from ..config import ServerConfig  # Legacy config
from ..services.config_service import (
    ConfigurationService,
    ServerConfiguration,
    get_configuration_service,
)
from ..services.dependency_injection import get_service, has_service


def get_server_configuration() -> ServerConfig | ServerConfiguration | None:
    """Get server configuration from new service or fall back to legacy.

    Returns:
        Server configuration instance (new or legacy format)
    """
    try:
        # Try new configuration service first
        if has_service(ConfigurationService):
            config_service = get_service(ConfigurationService)
            return config_service.get_server_config()
        else:
            config_service = get_configuration_service()
            return config_service.get_server_config()
    except Exception:
        # Fall back to legacy global variable access
        from .session_manager import _server_config

        return _server_config


def get_workflow_directory_path() -> Path | None:
    """Get workflow directory path from configuration.

    Returns:
        Path to workflows directory or None if not configured
    """
    config = get_server_configuration()
    if config is None:
        return None

    if hasattr(config, "workflows_dir"):
        return config.workflows_dir
    elif hasattr(config, "workflow_commander_dir"):
        return config.workflow_commander_dir / "workflows"

    return None


def get_sessions_directory_path() -> Path | None:
    """Get sessions directory path from configuration.

    Returns:
        Path to sessions directory or None if not configured
    """
    config = get_server_configuration()
    if config is None:
        return None

    if hasattr(config, "sessions_dir"):
        return config.sessions_dir
    elif hasattr(config, "workflow_commander_dir"):
        return config.workflow_commander_dir / "sessions"

    return None


def get_project_config_path() -> Path | None:
    """Get project configuration file path.

    Returns:
        Path to project_config.md or None if not configured
    """
    config = get_server_configuration()
    if config is None:
        return None

    if hasattr(config, "project_config_path"):
        return config.project_config_path
    elif hasattr(config, "workflow_commander_dir"):
        return config.workflow_commander_dir / "project_config.md"

    return None


def is_local_state_file_enabled() -> bool:
    """Check if local state file is enabled.

    Returns:
        True if local state file is enabled, False otherwise
    """
    config = get_server_configuration()
    if config is None:
        return False

    return getattr(config, "enable_local_state_file", False)


def get_local_state_file_format() -> str:
    """Get local state file format.

    Returns:
        Format string ('MD' or 'JSON'), defaults to 'MD'
    """
    config = get_server_configuration()
    if config is None:
        return "MD"

    return getattr(config, "local_state_file_format", "MD")


def is_cache_mode_enabled() -> bool:
    """Check if cache mode is enabled.

    Returns:
        True if cache mode is enabled, False otherwise
    """
    config = get_server_configuration()
    if config is None:
        return False

    return getattr(config, "enable_cache_mode", False)


def get_cache_directory_path() -> Path | None:
    """Get cache directory path from configuration.

    Returns:
        Path to cache directory or None if not configured
    """
    config = get_server_configuration()
    if config is None:
        return None

    if hasattr(config, "cache_dir"):
        return config.cache_dir
    elif hasattr(config, "workflow_commander_dir"):
        return config.workflow_commander_dir / "cache"

    return None


def ensure_workflow_directories() -> bool:
    """Ensure workflow-related directories exist.

    Returns:
        True if directories exist or were created successfully, False otherwise
    """
    config = get_server_configuration()
    if config is None:
        return False

    try:
        # Use legacy methods if available
        if hasattr(config, "ensure_workflow_commander_dir"):
            return config.ensure_workflow_commander_dir()
        elif hasattr(config, "ensure_workflows_dir"):
            return config.ensure_workflows_dir()

        # Fall back to manual directory creation
        workflow_dir = get_workflow_directory_path()
        if workflow_dir:
            workflow_dir.mkdir(parents=True, exist_ok=True)
            return True

        return False
    except Exception:
        return False


def ensure_sessions_directory() -> bool:
    """Ensure sessions directory exists.

    Returns:
        True if directory exists or was created successfully, False otherwise
    """
    config = get_server_configuration()
    if config is None:
        return False

    try:
        # Use legacy methods if available
        if hasattr(config, "ensure_sessions_dir"):
            return config.ensure_sessions_dir()

        # Fall back to manual directory creation
        sessions_dir = get_sessions_directory_path()
        if sessions_dir:
            sessions_dir.mkdir(parents=True, exist_ok=True)
            return True

        return False
    except Exception:
        return False
