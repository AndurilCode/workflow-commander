"""Services package for dev-workflow-mcp."""

# Service exports
from .config_service import (
    ConfigLocationSettings,
    ConfigurationError,
    ConfigurationService,
    ConfigurationServiceProtocol,
    ConfigurationValidationError,
    EnvironmentConfiguration,
    HandlerConfiguration,
    PlatformConfiguration,
    PlatformInfo,
    PlatformType,
    ServerConfiguration,
    WorkflowConfiguration,
    get_configuration_service,
    initialize_configuration_service,
    reset_configuration_service,
)
from .dependency_injection import (
    DependencyInjectionError,
    ServiceRegistry,
    clear_registry,
    get_service,
    get_service_registry,
    has_service,
    inject_config_service,
    inject_service,
    register_factory,
    register_service,
    register_singleton,
)
from .session_lifecycle_manager import (
    SessionLifecycleManager,
    SessionLifecycleManagerProtocol,
)
from .session_repository import (
    SessionRepository,
    SessionRepositoryProtocol,
)
from .session_service_factory import (
    SessionServiceFactory,
    get_session_lifecycle_manager,
    get_session_repository,
    get_session_service_factory,
    get_session_sync_service,
    get_workflow_definition_cache,
    initialize_session_services,
    reset_session_services,
)
from .session_sync_service import (
    SessionSyncService,
    SessionSyncServiceProtocol,
)
from .workflow_definition_cache import (
    WorkflowDefinitionCache,
    WorkflowDefinitionCacheProtocol,
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
    # Session Services
    "SessionRepository",
    "SessionRepositoryProtocol",
    "SessionSyncService",
    "SessionSyncServiceProtocol",
    "SessionLifecycleManager",
    "SessionLifecycleManagerProtocol",
    "WorkflowDefinitionCache",
    "WorkflowDefinitionCacheProtocol",
    # Session Service Factory
    "SessionServiceFactory",
    "get_session_service_factory",
    "initialize_session_services",
    "reset_session_services",
    "get_session_repository",
    "get_session_sync_service",
    "get_session_lifecycle_manager",
    "get_workflow_definition_cache",
]
