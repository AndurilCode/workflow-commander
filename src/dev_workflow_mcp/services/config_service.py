"""Configuration service for centralized configuration management."""

import os
import platform as platform_module
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, TypeVar, Union
from enum import Enum

from pydantic import BaseModel, Field

# Configuration model type
ConfigModel = TypeVar("ConfigModel", bound=BaseModel)


class PlatformType(str, Enum):
    """Supported AI platform types."""
    
    CURSOR = "cursor"
    CLAUDE_DESKTOP = "claude-desktop"
    CLAUDE_CODE = "claude-code"
    VSCODE = "vscode"


class ConfigLocationSettings(BaseModel):
    """Configuration file location settings for a platform."""
    
    global_path: Path = Field(..., description="Global configuration file path")
    project_path: Optional[Path] = Field(
        default=None, description="Project-specific configuration path"
    )
    description: str = Field(
        ..., description="Human-readable description of the location"
    )
    
    def get_global_path(self) -> Path:
        """Get the expanded global configuration path."""
        return Path(os.path.expanduser(str(self.global_path)))

    def get_project_path(self, project_root: Optional[Path] = None) -> Optional[Path]:
        """Get the project configuration path relative to project root."""
        if self.project_path is None:
            return None

        if project_root is None:
            project_root = Path.cwd()

        return project_root / self.project_path


class PlatformInfo(BaseModel):
    """Comprehensive platform information and configuration."""
    
    name: str = Field(..., description="Platform display name")
    platform_type: PlatformType = Field(..., description="Platform type enum")
    description: str = Field(..., description="Platform description")
    config_format: str = Field(
        ..., description="Configuration format (e.g., 'mcpServers' or 'mcp.servers')"
    )
    locations: ConfigLocationSettings = Field(..., description="Configuration file locations")
    supported_transports: List[str] = Field(
        default_factory=list, description="Supported MCP transport types"
    )
    documentation_url: Optional[str] = Field(
        default=None, description="Link to platform documentation"
    )
    
    @classmethod
    def get_platform_info(cls, platform_type: PlatformType) -> "PlatformInfo":
        """Get platform information for a specific platform type."""
        system = platform_module.system().lower()
        
        if platform_type == PlatformType.CURSOR:
            if system == "windows":
                global_path = Path("~/AppData/Roaming/Cursor/User/mcp.json")
            elif system == "darwin":  # macOS
                global_path = Path("~/Library/Application Support/Cursor/User/mcp.json")
            else:  # Linux and others
                global_path = Path("~/.config/Cursor/User/mcp.json")
            
            return cls(
                name="Cursor",
                platform_type=PlatformType.CURSOR,
                description="Modern AI-powered code editor with built-in AI assistance",
                config_format="mcpServers",
                locations=ConfigLocationSettings(
                    global_path=global_path,
                    project_path=Path(".cursor/mcp.json"),
                    description="User settings directory or project .cursor folder",
                ),
                supported_transports=["stdio", "sse", "streamable-http"],
                documentation_url="https://docs.cursor.com/advanced/mcp",
            )
        
        elif platform_type == PlatformType.CLAUDE_DESKTOP:
            if system == "windows":
                global_path = Path("~/AppData/Roaming/Claude/claude_desktop_config.json")
            elif system == "darwin":  # macOS
                global_path = Path("~/Library/Application Support/Claude/claude_desktop_config.json")
            else:  # Linux and others
                global_path = Path("~/.config/Claude/claude_desktop_config.json")
            
            return cls(
                name="Claude Desktop",
                platform_type=PlatformType.CLAUDE_DESKTOP,
                description="Anthropic's desktop application for Claude AI",
                config_format="mcpServers",
                locations=ConfigLocationSettings(
                    global_path=global_path,
                    project_path=None,  # Claude Desktop doesn't support project configs
                    description="Application support directory",
                ),
                supported_transports=["stdio"],
                documentation_url="https://modelcontextprotocol.io/quickstart/user",
            )
        
        elif platform_type == PlatformType.CLAUDE_CODE:
            return cls(
                name="Claude Code",
                platform_type=PlatformType.CLAUDE_CODE,
                description="Anthropic's command-line coding assistant",
                config_format="mcpServers",
                locations=ConfigLocationSettings(
                    global_path=Path("~/.mcp.json"),  # Global fallback, though rarely used
                    project_path=Path(".mcp.json"),  # Primary location for Claude Code
                    description="Project root directory or user home directory",
                ),
                supported_transports=["stdio"],
                documentation_url="https://docs.anthropic.com/en/docs/claude-code/tutorials#set-up-model-context-protocol-mcp",
            )
        
        elif platform_type == PlatformType.VSCODE:
            if system == "windows":
                global_path = Path("~/AppData/Roaming/Code/User/settings.json")
            elif system == "darwin":  # macOS
                global_path = Path("~/Library/Application Support/Code/User/settings.json")
            else:  # Linux and others
                global_path = Path("~/.config/Code/User/settings.json")
            
            return cls(
                name="VS Code",
                platform_type=PlatformType.VSCODE,
                description="Visual Studio Code with GitHub Copilot integration",
                config_format="mcp.servers",
                locations=ConfigLocationSettings(
                    global_path=global_path,
                    project_path=Path(".vscode/settings.json"),
                    description="User settings or workspace .vscode folder",
                ),
                supported_transports=["stdio", "sse"],
                documentation_url="https://code.visualstudio.com/docs",
            )
        
        else:
            raise ValueError(f"Unsupported platform type: {platform_type}")


class HandlerConfiguration(BaseModel):
    """Configuration for platform-specific handlers."""
    
    handler_class: str = Field(..., description="Handler class name")
    module_path: str = Field(..., description="Python module path for the handler")
    config_validation: bool = Field(
        default=True, description="Enable configuration validation"
    )
    backup_configs: bool = Field(
        default=True, description="Create backup copies of configuration files"
    )
    merge_strategy: str = Field(
        default="preserve_existing", 
        description="Strategy for merging configurations (preserve_existing, replace, merge)"
    )


class ConfigurationServiceProtocol(Protocol):
    """Protocol defining the configuration service interface."""

    def get_server_config(self) -> "ServerConfiguration":
        """Get server configuration."""
        ...

    def get_workflow_config(self) -> "WorkflowConfiguration":
        """Get workflow configuration."""
        ...

    def get_platform_config(self) -> "PlatformConfiguration":
        """Get platform configuration."""
        ...

    def get_environment_config(self) -> "EnvironmentConfiguration":
        """Get environment-specific configuration."""
        ...

    def validate_configuration(self) -> tuple[bool, list[str]]:
        """Validate all configuration components."""
        ...

    def reload_configuration(self) -> bool:
        """Reload configuration from sources."""
        ...


class ConfigurationError(Exception):
    """Base exception for configuration-related errors."""
    pass


class ConfigurationValidationError(ConfigurationError):
    """Exception raised when configuration validation fails."""
    pass


# Configuration Models
class ServerConfiguration(BaseModel):
    """Server-specific configuration settings."""
    
    repository_path: Path = Field(
        default_factory=lambda: Path.cwd(),
        description="Repository root path where .workflow-commander folder is located"
    )
    
    # Session management
    enable_local_state_file: bool = Field(
        default=False,
        description="Enable automatic synchronization of workflow state to local files"
    )
    
    local_state_file_format: str = Field(
        default="MD",
        description="Format for local state files (MD or JSON)"
    )
    
    session_retention_hours: int = Field(
        default=168,  # 7 days
        description="Hours to keep completed sessions before cleanup"
    )
    
    enable_session_archiving: bool = Field(
        default=True,
        description="Enable archiving of session files before cleanup"
    )
    
    # Cache configuration
    enable_cache_mode: bool = Field(
        default=False,
        description="Enable ChromaDB-based caching for workflow state persistence"
    )
    
    cache_db_path: Optional[str] = Field(
        default=None,
        description="Path to ChromaDB database directory"
    )
    
    cache_collection_name: str = Field(
        default="workflow_states",
        description="Name of ChromaDB collection for workflow states"
    )
    
    cache_embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="Sentence transformer model for semantic embeddings"
    )
    
    cache_max_results: int = Field(
        default=50,
        description="Maximum number of results for semantic search queries"
    )

    @property
    def workflow_commander_dir(self) -> Path:
        """Get the .workflow-commander directory path."""
        return self.repository_path / ".workflow-commander"

    @property
    def workflows_dir(self) -> Path:
        """Get the workflows directory path."""
        return self.workflow_commander_dir / "workflows"

    @property
    def project_config_path(self) -> Path:
        """Get the project configuration file path."""
        return self.workflow_commander_dir / "project_config.md"

    @property
    def sessions_dir(self) -> Path:
        """Get the sessions directory path."""
        return self.workflow_commander_dir / "sessions"

    @property
    def cache_dir(self) -> Path:
        """Get the cache directory path."""
        if self.cache_db_path:
            return Path(self.cache_db_path)
        return self.workflow_commander_dir / "cache"


class WorkflowConfiguration(BaseModel):
    """Workflow behavior configuration."""
    
    local_state_file: bool = Field(
        default=False,
        description="Enforce local storage of workflow state files"
    )
    
    local_state_file_format: str = Field(
        default="MD",
        description="Format for local state files when local_state_file is enabled"
    )
    
    default_max_depth: int = Field(
        default=10,
        description="Default maximum depth for workflow execution"
    )
    
    allow_backtracking: bool = Field(
        default=True,
        description="Allow backtracking in workflow execution"
    )


class PlatformConfiguration(BaseModel):
    """Platform-specific configuration settings."""
    
    # Core platform settings
    editor_type: PlatformType = Field(
        default=PlatformType.CURSOR,
        description="Primary editor platform"
    )
    
    cli_enabled: bool = Field(
        default=True,
        description="Enable CLI command integration"
    )
    
    # Platform information and locations
    platform_info: Optional[PlatformInfo] = Field(
        default=None,
        description="Detailed platform information"
    )
    
    # Handler configuration
    handler_config: Optional[HandlerConfiguration] = Field(
        default=None,
        description="Platform-specific handler configuration"
    )
    
    # Configuration file management
    config_file_management: Dict[str, Union[str, bool]] = Field(
        default_factory=lambda: {
            "auto_backup": True,
            "backup_retention_days": 7,
            "merge_strategy": "preserve_existing",
            "validate_on_save": True,
        },
        description="Configuration file management settings"
    )
    
    # Environment variables for platform integration
    environment_variables: Dict[str, str] = Field(
        default_factory=dict,
        description="Platform-specific environment variables"
    )
    
    # CLI integration settings  
    cli_integration: Dict[str, Union[str, bool, List[str]]] = Field(
        default_factory=lambda: {
            "enable_auto_detection": True,
            "preferred_config_location": "global",
            "supported_commands": ["configure", "list-servers", "remove-server", "validate"],
            "non_interactive_defaults": True,
        },
        description="CLI integration configuration"
    )
    
    # Transport and communication settings
    transport_settings: Dict[str, Union[str, int, List[str]]] = Field(
        default_factory=lambda: {
            "preferred_transport": "stdio",
            "fallback_transports": ["stdio"],
            "timeout_seconds": 30,
        },
        description="MCP transport configuration"
    )
    
    def __init__(self, **data):
        """Initialize platform configuration with auto-detection."""
        super().__init__(**data)
        
        # Auto-populate platform info if not provided
        if self.platform_info is None:
            self.platform_info = PlatformInfo.get_platform_info(self.editor_type)
        
        # Auto-configure handler if not provided
        if self.handler_config is None:
            self.handler_config = self._get_default_handler_config()
    
    def _get_default_handler_config(self) -> HandlerConfiguration:
        """Get default handler configuration for the platform."""
        handler_map = {
            PlatformType.CURSOR: HandlerConfiguration(
                handler_class="CursorHandler",
                module_path="workflow_commander_cli.handlers.cursor",
            ),
            PlatformType.CLAUDE_DESKTOP: HandlerConfiguration(
                handler_class="ClaudeDesktopHandler", 
                module_path="workflow_commander_cli.handlers.claude",
            ),
            PlatformType.CLAUDE_CODE: HandlerConfiguration(
                handler_class="ClaudeCodeHandler",
                module_path="workflow_commander_cli.handlers.claude", 
            ),
            PlatformType.VSCODE: HandlerConfiguration(
                handler_class="VSCodeHandler",
                module_path="workflow_commander_cli.handlers.vscode",
            ),
        }
        
        return handler_map.get(self.editor_type, HandlerConfiguration(
            handler_class="BaseConfigHandler",
            module_path="workflow_commander_cli.handlers.base",
        ))
    
    def get_config_location(self, use_global: bool = True, project_root: Optional[Path] = None) -> Path:
        """Get configuration file location for the platform."""
        if not self.platform_info:
            raise ValueError("Platform info not configured")
        
        if use_global:
            return self.platform_info.locations.get_global_path()
        else:
            project_path = self.platform_info.locations.get_project_path(project_root)
            if project_path is None:
                # Fallback to global if no project path available
                return self.platform_info.locations.get_global_path()
            return project_path
    
    def get_supported_transports(self) -> List[str]:
        """Get supported transport types for the platform."""
        if self.platform_info:
            return self.platform_info.supported_transports
        return self.transport_settings.get("fallback_transports", ["stdio"])
    
    def validate_platform_compatibility(self) -> tuple[bool, List[str]]:
        """Validate platform compatibility and configuration."""
        issues = []
        
        # Check if platform info is available
        if not self.platform_info:
            issues.append("Platform information not available")
            return False, issues
        
        # Check if global config directory is accessible
        try:
            global_path = self.platform_info.locations.get_global_path()
            global_path.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            issues.append(f"Cannot access global config directory: {e}")
        
        # Validate transport settings
        supported = self.get_supported_transports()
        preferred = self.transport_settings.get("preferred_transport", "stdio")
        if preferred not in supported:
            issues.append(f"Preferred transport '{preferred}' not supported by platform")
        
        return len(issues) == 0, issues


class EnvironmentConfiguration(BaseModel):
    """Environment-specific configuration (S3, external services)."""
    
    # S3 Configuration
    s3_enabled: bool = Field(
        default_factory=lambda: bool(os.getenv("S3_BUCKET_NAME")),
        description="Enable S3 synchronization"
    )
    
    s3_bucket_name: Optional[str] = Field(
        default_factory=lambda: os.getenv("S3_BUCKET_NAME"),
        description="S3 bucket name"
    )
    
    s3_prefix: str = Field(
        default_factory=lambda: os.getenv("S3_PREFIX", "workflow-states/"),
        description="S3 key prefix for workflow states"
    )
    
    s3_region: str = Field(
        default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"),
        description="AWS region"
    )
    
    s3_sync_on_finalize: bool = Field(
        default_factory=lambda: os.getenv("S3_SYNC_ON_FINALIZE", "true").lower() == "true",
        description="Sync state when workflow is finalized"
    )
    
    s3_archive_completed: bool = Field(
        default_factory=lambda: os.getenv("S3_ARCHIVE_COMPLETED", "true").lower() == "true",
        description="Archive completed workflows with timestamp"
    )


class ConfigurationService:
    """Centralized configuration service implementation."""
    
    def __init__(
        self,
        server_config: Optional[ServerConfiguration] = None,
        workflow_config: Optional[WorkflowConfiguration] = None,
        platform_config: Optional[PlatformConfiguration] = None,
        environment_config: Optional[EnvironmentConfiguration] = None,
    ):
        """Initialize configuration service.
        
        Args:
            server_config: Server configuration instance
            workflow_config: Workflow configuration instance  
            platform_config: Platform configuration instance
            environment_config: Environment configuration instance
        """
        self._server_config = server_config or ServerConfiguration()
        self._workflow_config = workflow_config or WorkflowConfiguration()
        self._platform_config = platform_config or PlatformConfiguration()
        self._environment_config = environment_config or EnvironmentConfiguration()
        
        # Validate configuration on initialization
        is_valid, errors = self.validate_configuration()
        if not is_valid:
            raise ConfigurationValidationError(f"Configuration validation failed: {errors}")
    
    def get_server_config(self) -> ServerConfiguration:
        """Get server configuration."""
        return self._server_config
    
    def get_workflow_config(self) -> WorkflowConfiguration:
        """Get workflow configuration."""
        return self._workflow_config
    
    def get_platform_config(self) -> PlatformConfiguration:
        """Get platform configuration."""
        return self._platform_config
    
    def get_environment_config(self) -> EnvironmentConfiguration:
        """Get environment-specific configuration."""
        return self._environment_config
    
    def validate_configuration(self) -> tuple[bool, list[str]]:
        """Validate all configuration components.
        
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        # Validate server configuration
        server_config = self._server_config
        
        # Check repository path
        if not server_config.repository_path.exists():
            issues.append(f"Repository path does not exist: {server_config.repository_path}")
        elif not server_config.repository_path.is_dir():
            issues.append(f"Repository path is not a directory: {server_config.repository_path}")
        
        # Check workflow configuration format
        workflow_config = self._workflow_config
        if workflow_config.local_state_file_format.upper() not in ("MD", "JSON"):
            issues.append(f"Invalid local_state_file_format: {workflow_config.local_state_file_format}")
        
        # Check environment configuration consistency
        env_config = self._environment_config
        if env_config.s3_enabled and not env_config.s3_bucket_name:
            issues.append("S3 sync is enabled but bucket_name is not set")
        
        return len(issues) == 0, issues
    
    def reload_configuration(self) -> bool:
        """Reload configuration from sources.
        
        Returns:
            True if reload was successful, False otherwise
        """
        try:
            # Reload environment configuration
            self._environment_config = EnvironmentConfiguration()
            
            # Re-validate after reload
            is_valid, _ = self.validate_configuration()
            return is_valid
        except Exception:
            return False
    
    def update_server_config(self, **kwargs) -> None:
        """Update server configuration with new values."""
        for key, value in kwargs.items():
            if hasattr(self._server_config, key):
                setattr(self._server_config, key, value)
        
        # Re-validate after update
        is_valid, errors = self.validate_configuration()
        if not is_valid:
            raise ConfigurationValidationError(f"Configuration update failed validation: {errors}")
    
    def to_legacy_server_config(self) -> "ServerConfig":
        """Convert to legacy ServerConfig for backward compatibility.
        
        Returns:
            Legacy ServerConfig instance
        """
        from ..config import ServerConfig
        
        server_cfg = self._server_config
        return ServerConfig(
            repository_path=str(server_cfg.repository_path),
            enable_local_state_file=server_cfg.enable_local_state_file,
            local_state_file_format=server_cfg.local_state_file_format,
            session_retention_hours=server_cfg.session_retention_hours,
            enable_session_archiving=server_cfg.enable_session_archiving,
            enable_cache_mode=server_cfg.enable_cache_mode,
            cache_db_path=server_cfg.cache_db_path,
            cache_collection_name=server_cfg.cache_collection_name,
            cache_embedding_model=server_cfg.cache_embedding_model,
            cache_max_results=server_cfg.cache_max_results,
        )


# Global configuration service instance
_config_service: Optional[ConfigurationService] = None


def get_configuration_service() -> ConfigurationService:
    """Get the global configuration service instance.
    
    Returns:
        ConfigurationService instance
        
    Raises:
        ConfigurationError: If configuration service is not initialized
    """
    global _config_service
    if _config_service is None:
        raise ConfigurationError("Configuration service not initialized. Call initialize_configuration_service() first.")
    return _config_service


def initialize_configuration_service(
    server_config: Optional[ServerConfiguration] = None,
    workflow_config: Optional[WorkflowConfiguration] = None,
    platform_config: Optional[PlatformConfiguration] = None,
    environment_config: Optional[EnvironmentConfiguration] = None,
) -> ConfigurationService:
    """Initialize the global configuration service.
    
    Args:
        server_config: Server configuration instance
        workflow_config: Workflow configuration instance
        platform_config: Platform configuration instance
        environment_config: Environment configuration instance
        
    Returns:
        ConfigurationService instance
    """
    global _config_service
    _config_service = ConfigurationService(
        server_config=server_config,
        workflow_config=workflow_config,
        platform_config=platform_config,
        environment_config=environment_config,
    )
    return _config_service


def reset_configuration_service() -> None:
    """Reset the global configuration service (primarily for testing)."""
    global _config_service
    _config_service = None 