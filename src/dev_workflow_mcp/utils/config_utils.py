"""Configuration utility functions for workflow MCP server."""

from ..models.config import WorkflowConfig  # Keep for backward compatibility
from ..services.config_service import (
    ConfigurationService,
    WorkflowConfiguration,
    get_configuration_service,
)
from ..services.dependency_injection import get_service, has_service


def get_workflow_config(server_config=None) -> WorkflowConfig:
    """Get workflow configuration instance.

    Args:
        server_config: Optional ServerConfig instance with CLI-provided values.
                      If None, uses default values or configuration service.

    Returns:
        WorkflowConfig: Configuration instance (legacy format for backward compatibility)
    """
    # Try to use new configuration service first
    try:
        if has_service(ConfigurationService):
            config_service = get_service(ConfigurationService)
            workflow_config = config_service.get_workflow_config()

            # Convert to legacy WorkflowConfig for backward compatibility
            return WorkflowConfig(
                local_state_file=workflow_config.local_state_file,
                local_state_file_format=workflow_config.local_state_file_format,
            )
        elif server_config is None:
            # Try global configuration service
            config_service = get_configuration_service()
            workflow_config = config_service.get_workflow_config()

            # Convert to legacy WorkflowConfig for backward compatibility
            return WorkflowConfig(
                local_state_file=workflow_config.local_state_file,
                local_state_file_format=workflow_config.local_state_file_format,
            )
    except Exception:
        # Fall back to legacy behavior if configuration service is not available
        pass

    # Legacy behavior for backward compatibility
    if server_config:
        return WorkflowConfig.from_server_config(server_config)
    else:
        # Default configuration for backward compatibility
        return WorkflowConfig()


def get_workflow_configuration_service() -> WorkflowConfiguration | None:
    """Get workflow configuration from the new configuration service.

    Returns:
        WorkflowConfiguration instance if available, None otherwise
    """
    try:
        if has_service(ConfigurationService):
            config_service = get_service(ConfigurationService)
            return config_service.get_workflow_config()
        else:
            config_service = get_configuration_service()
            return config_service.get_workflow_config()
    except Exception:
        return None
