# Configuration Service Architecture

## Overview

The Configuration Service provides a centralized, type-safe, and extensible configuration management system for the dev-workflow-mcp project. This service replaces scattered configuration handling with a clean, dependency-injection-based architecture.

## Architecture Components

### Core Configuration Models

#### ServerConfiguration
Manages server-level settings including repository paths, session management, and cache configuration.

```python
from src.dev_workflow_mcp.services import ServerConfiguration

server_config = ServerConfiguration(
    repository_path=Path("/path/to/project"),
    enable_local_state_file=True,
    local_state_file_format="JSON",
    session_retention_hours=168,
    enable_cache_mode=True,
    cache_db_path="/path/to/cache",
    cache_collection_name="workflow_states",
    cache_embedding_model="all-MiniLM-L6-v2",
    cache_max_results=50
)
```

#### WorkflowConfiguration
Handles workflow execution settings and behavior configuration.

```python
from src.dev_workflow_mcp.services import WorkflowConfiguration

workflow_config = WorkflowConfiguration(
    local_state_file_format="MD",
    default_max_depth=10,
    enable_backtracking=True,
    auto_save_state=True,
    validation_mode="strict"
)
```

#### PlatformConfiguration
Manages platform-specific settings for different AI development environments.

```python
from src.dev_workflow_mcp.services import PlatformConfiguration, PlatformType

platform_config = PlatformConfiguration(
    editor_type=PlatformType.CURSOR,
    cli_enabled=True,
    environment_variables={"EDITOR": "cursor"},
    transport_settings={
        "preferred_transport": "stdio",
        "fallback_transports": ["stdio"],
        "timeout_seconds": 30
    }
)
```

#### EnvironmentConfiguration
Handles environment-specific settings including S3 integration and external services.

```python
from src.dev_workflow_mcp.services import EnvironmentConfiguration

env_config = EnvironmentConfiguration(
    s3_bucket_name="my-workflow-bucket",
    aws_region="us-east-1",
    s3_enabled=True
)
```

### Configuration Service

The `ConfigurationService` provides a unified interface for accessing all configuration components:

```python
from src.dev_workflow_mcp.services import (
    ConfigurationService,
    initialize_configuration_service,
    get_configuration_service
)

# Initialize the service
config_service = initialize_configuration_service(
    server_config=server_config,
    workflow_config=workflow_config,
    platform_config=platform_config,
    environment_config=env_config
)

# Access configurations
server_cfg = config_service.get_server_config()
workflow_cfg = config_service.get_workflow_config()
platform_cfg = config_service.get_platform_config()
env_cfg = config_service.get_environment_config()

# Validate configuration
is_valid, errors = config_service.validate_configuration()
```

### Dependency Injection Framework

The service includes a comprehensive dependency injection system:

```python
from src.dev_workflow_mcp.services import (
    register_singleton,
    get_service,
    inject_config_service
)

# Register services
register_singleton(ConfigurationService, config_service)

# Inject into functions
@inject_config_service
def my_function(config_service: ConfigurationService):
    server_config = config_service.get_server_config()
    # Use configuration...

# Get services directly
config_service = get_service(ConfigurationService)
```

## Migration from Legacy Configuration

### Before (Legacy)
```python
# Scattered configuration access
from src.dev_workflow_mcp.config import ServerConfig
from src.dev_workflow_mcp.utils.session_manager import set_server_config

config = ServerConfig(repository_path=".")
set_server_config(config)

# Global variable access
global _server_config
if _server_config:
    sessions_dir = _server_config.sessions_dir
```

### After (New Service)
```python
# Centralized configuration service
from src.dev_workflow_mcp.services import (
    ServerConfiguration,
    initialize_configuration_service,
    get_configuration_service
)

server_config = ServerConfiguration(repository_path=Path("."))
config_service = initialize_configuration_service(server_config=server_config)

# Clean service access
config_service = get_configuration_service()
server_config = config_service.get_server_config()
sessions_dir = server_config.sessions_dir
```

## Configuration Validation

The service provides comprehensive validation:

```python
# Automatic validation during initialization
try:
    config_service = initialize_configuration_service(
        server_config=invalid_config
    )
except ConfigurationValidationError as e:
    print(f"Configuration error: {e}")

# Manual validation
is_valid, errors = config_service.validate_configuration()
if not is_valid:
    for error in errors:
        print(f"Validation error: {error}")
```

## Platform-Specific Configuration

### Cursor Integration
```python
platform_config = PlatformConfiguration(
    editor_type=PlatformType.CURSOR,
    cli_enabled=True,
    config_file_management={
        "auto_update": True,
        "backup_configs": True
    },
    transport_settings={
        "preferred_transport": "stdio"
    }
)
```

### VS Code Integration
```python
platform_config = PlatformConfiguration(
    editor_type=PlatformType.VSCODE,
    cli_enabled=False,
    config_file_management={
        "config_format": "mcp.servers",
        "auto_update": False
    }
)
```

## Environment Configuration

### S3 Integration
```python
env_config = EnvironmentConfiguration(
    s3_bucket_name=os.getenv("S3_BUCKET_NAME"),
    aws_region=os.getenv("AWS_REGION", "us-east-1"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

# Automatic S3 detection
if env_config.s3_enabled:
    print("S3 integration available")
```

## Best Practices

### 1. Use Dependency Injection
```python
# Good: Use dependency injection
@inject_config_service
def process_workflow(config_service: ConfigurationService):
    server_config = config_service.get_server_config()
    # Process with configuration

# Avoid: Direct global access
# global _server_config  # Don't do this
```

### 2. Validate Early
```python
# Initialize and validate configuration at startup
try:
    config_service = initialize_configuration_service(
        server_config=server_config,
        workflow_config=workflow_config,
        platform_config=platform_config,
        environment_config=environment_config
    )
    
    is_valid, errors = config_service.validate_configuration()
    if not is_valid:
        raise ConfigurationValidationError(f"Configuration errors: {errors}")
        
except ConfigurationValidationError as e:
    print(f"Configuration error: {e}")
    sys.exit(1)
```

### 3. Use Type-Safe Configuration Access
```python
# Good: Type-safe access
server_config: ServerConfiguration = config_service.get_server_config()
cache_dir: Path = server_config.cache_dir

# Avoid: Untyped access
# config = get_some_config()  # What type is this?
```

### 4. Leverage Backward Compatibility
```python
# For legacy code that needs ServerConfig
legacy_config = config_service.to_legacy_server_config()

# Gradually migrate to new service
# Old: set_server_config(legacy_config)
# New: Use config_service directly
```

## Error Handling

### Configuration Validation Errors
```python
from src.dev_workflow_mcp.services import ConfigurationValidationError

try:
    config_service = initialize_configuration_service(
        server_config=ServerConfiguration(repository_path=Path("/nonexistent"))
    )
except ConfigurationValidationError as e:
    print(f"Configuration validation failed: {e}")
    # Handle error appropriately
```

### Service Not Initialized
```python
from src.dev_workflow_mcp.services import ConfigurationError

try:
    config_service = get_configuration_service()
except ConfigurationError as e:
    print(f"Configuration service not initialized: {e}")
    # Initialize service or handle error
```

## Testing Configuration

### Unit Testing
```python
def test_server_configuration():
    config = ServerConfiguration(
        repository_path=Path("/tmp/test"),
        enable_local_state_file=True
    )
    
    assert config.repository_path == Path("/tmp/test")
    assert config.enable_local_state_file is True
    assert config.sessions_dir == Path("/tmp/test/.workflow-commander/sessions")
```

### Integration Testing
```python
def test_configuration_service_integration():
    server_config = ServerConfiguration(repository_path=Path("."))
    config_service = initialize_configuration_service(server_config=server_config)
    
    # Test service functionality
    retrieved_config = config_service.get_server_config()
    assert retrieved_config.repository_path == Path(".")
    
    # Test validation
    is_valid, errors = config_service.validate_configuration()
    assert is_valid
    assert len(errors) == 0
```

## Performance Considerations

### Lazy Loading
Configuration components are loaded lazily to improve startup performance:

```python
# Platform info is computed on first access
platform_config = PlatformConfiguration()
platform_info = platform_config.platform_info  # Computed here
```

### Caching
Configuration values are cached to avoid repeated computation:

```python
# Cached property access
server_config = ServerConfiguration(repository_path=Path("."))
cache_dir = server_config.cache_dir  # Computed once
cache_dir_again = server_config.cache_dir  # Cached value
```

### Memory Efficiency
The service uses singleton patterns to minimize memory usage:

```python
# Single instance across application
config_service = get_configuration_service()  # Same instance
another_ref = get_configuration_service()     # Same instance
assert config_service is another_ref
```

## Troubleshooting

### Common Issues

1. **Configuration Service Not Initialized**
   ```python
   # Error: ConfigurationError: Configuration service not initialized
   # Solution: Initialize before use
   config_service = initialize_configuration_service(server_config=server_config)
   ```

2. **Invalid Repository Path**
   ```python
   # Error: ConfigurationValidationError: Repository path does not exist
   # Solution: Ensure path exists or create it
   repository_path = Path("/path/to/project")
   repository_path.mkdir(parents=True, exist_ok=True)
   ```

3. **S3 Configuration Issues**
   ```python
   # Error: S3 credentials not found
   # Solution: Set environment variables
   os.environ["AWS_ACCESS_KEY_ID"] = "your-key"
   os.environ["AWS_SECRET_ACCESS_KEY"] = "your-secret"
   ```

### Debug Mode
Enable debug logging for configuration issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Configuration service will log debug information
config_service = initialize_configuration_service(server_config=server_config)
```

## Future Enhancements

### Planned Features
- Configuration hot-reloading
- Remote configuration sources
- Configuration encryption
- Advanced validation rules
- Configuration versioning

### Extension Points
The service is designed for extensibility:

```python
# Custom configuration models
class CustomConfiguration(BaseModel):
    custom_setting: str = "default"

# Custom validation
def custom_validator(config: CustomConfiguration) -> tuple[bool, list[str]]:
    errors = []
    if not config.custom_setting:
        errors.append("Custom setting is required")
    return len(errors) == 0, errors
``` 