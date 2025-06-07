"""Services package for dev-workflow-mcp."""

# Service exports
from .config_service import (
    ConfigurationService,
    ConfigurationServiceProtocol,
    ConfigurationError,
    ConfigurationValidationError,
    ServerConfiguration,
    WorkflowConfiguration,
    PlatformConfiguration,
    PlatformType,
    PlatformInfo,
    ConfigLocationSettings,
    HandlerConfiguration,
    EnvironmentConfiguration,
    get_configuration_service,
    initialize_configuration_service,
    reset_configuration_service,
)
from .dependency_injection import (
    ServiceRegistry,
    DependencyInjectionError,
    get_service_registry,
    register_service,
    register_factory,
    register_singleton,
    get_service,
    has_service,
    clear_registry,
    inject_service,
    inject_config_service,
)

__all__ = [
    # Configuration Service
    "ConfigurationService",
    "ConfigurationServiceProtocol",
    "ConfigurationError",
    "ConfigurationValidationError",
    "ServerConfiguration",
    "WorkflowConfiguration",
    "PlatformConfiguration",
    "PlatformType",
    "PlatformInfo",
    "ConfigLocationSettings",
    "HandlerConfiguration",
    "EnvironmentConfiguration",
    "get_configuration_service",
    "initialize_configuration_service",
    "reset_configuration_service",
    # Dependency Injection
    "ServiceRegistry",
    "DependencyInjectionError",
    "get_service_registry",
    "register_service",
    "register_factory",
    "register_singleton",
    "get_service",
    "has_service",
    "clear_registry",
    "inject_service",
    "inject_config_service",
] 