"""Configuration management for the MCP server."""

from pathlib import Path


class ServerConfig:
    """Configuration settings for the MCP server."""

    def __init__(
        self,
        repository_path: str | None = None,
        enable_local_state_file: bool = False,
        local_state_file_format: str = "MD",
        session_retention_hours: int = 168,  # 7 days default
        enable_session_archiving: bool = True,
        enable_cache_mode: bool = False,
        cache_db_path: str | None = None,
        cache_collection_name: str = "workflow_states",
        cache_embedding_model: str = "all-MiniLM-L6-v2",
        cache_max_results: int = 50,
    ):
        """Initialize server configuration.

        Args:
            repository_path: Optional path to the repository root where .workflow-commander
                           folder should be located. Defaults to current directory.
            enable_local_state_file: Enable automatic synchronization of workflow state
                                   to local files in .workflow-commander/sessions/.
            local_state_file_format: Format for local state files ('MD' or 'JSON').
            session_retention_hours: Hours to keep completed sessions before cleanup (default: 168 = 7 days).
            enable_session_archiving: Whether to archive session files before cleanup (default: True).
            enable_cache_mode: Enable ChromaDB-based caching for workflow state persistence (default: False).
            cache_db_path: Path to ChromaDB database directory. Defaults to .workflow-commander/cache.
            cache_collection_name: Name of ChromaDB collection for workflow states (default: workflow_states).
            cache_embedding_model: Sentence transformer model for semantic embeddings (default: all-MiniLM-L6-v2).
            cache_max_results: Maximum number of results for semantic search queries (default: 50).
        """
        if repository_path:
            self.repository_path = Path(repository_path).resolve()
        else:
            self.repository_path = Path.cwd()

        # Validate the repository path exists
        if not self.repository_path.exists():
            raise ValueError(f"Repository path does not exist: {self.repository_path}")

        if not self.repository_path.is_dir():
            raise ValueError(
                f"Repository path is not a directory: {self.repository_path}"
            )

        # Store session storage configuration
        self.enable_local_state_file = enable_local_state_file

        # Validate and normalize format
        format_upper = local_state_file_format.upper()
        if format_upper not in ("MD", "JSON"):
            raise ValueError(
                f"local_state_file_format must be 'MD' or 'JSON', got '{local_state_file_format}'"
            )
        self.local_state_file_format = format_upper

        # Store session management configuration
        self.session_retention_hours = max(1, session_retention_hours)  # Minimum 1 hour
        self.enable_session_archiving = enable_session_archiving

        # Store cache configuration
        self.enable_cache_mode = enable_cache_mode

        # Fix: Resolve cache_db_path relative to repository_path for relative paths
        if cache_db_path:
            cache_path = Path(cache_db_path)
            if cache_path.is_absolute():
                # Absolute path: use as-is
                self.cache_db_path = str(cache_path)
            else:
                # Relative path: resolve relative to repository_path
                self.cache_db_path = str(self.repository_path / cache_path)
        else:
            # Default: use .workflow-commander/cache in repository
            self.cache_db_path = str(self.workflow_commander_dir / "cache")

        self.cache_collection_name = cache_collection_name
        self.cache_embedding_model = cache_embedding_model
        self.cache_max_results = max(1, cache_max_results)  # Minimum 1 result

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
        return Path(self.cache_db_path)

    def ensure_workflow_commander_dir(self) -> bool:
        """Ensure the .workflow-commander directory exists.

        Returns:
            True if directory exists or was created successfully, False otherwise.
        """
        try:
            self.workflow_commander_dir.mkdir(exist_ok=True)
            return True
        except (OSError, PermissionError):
            return False

    def ensure_workflows_dir(self) -> bool:
        """Ensure the workflows directory exists.

        Returns:
            True if directory exists or was created successfully, False otherwise.
        """
        try:
            if self.ensure_workflow_commander_dir():
                self.workflows_dir.mkdir(exist_ok=True)
                return True
            return False
        except (OSError, PermissionError):
            return False

    def ensure_sessions_dir(self) -> bool:
        """Ensure the sessions directory exists.

        Returns:
            True if directory exists or was created successfully, False otherwise.
        """
        try:
            if self.ensure_workflow_commander_dir():
                self.sessions_dir.mkdir(exist_ok=True)
                return True
            return False
        except (OSError, PermissionError):
            return False

    def ensure_cache_dir(self) -> bool:
        """Ensure the cache directory exists.

        Returns:
            True if directory exists or was created successfully, False otherwise.
        """
        try:
            if self.enable_cache_mode:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                return True
            return True  # Not needed if cache mode disabled
        except (OSError, PermissionError):
            return False

    def get_sessions_dir(self) -> Path:
        """Get the sessions directory path (compatibility method).
        
        Returns:
            Path to the sessions directory.
        """
        return self.sessions_dir

    def validate_configuration(self) -> tuple[bool, list[str]]:
        """Validate the configuration and provide status information.

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        # Check repository path
        if not self.repository_path.exists():
            issues.append(f"Repository path does not exist: {self.repository_path}")
        elif not self.repository_path.is_dir():
            issues.append(f"Repository path is not a directory: {self.repository_path}")

        # Check .workflow-commander directory (not required to exist)
        if (
            self.workflow_commander_dir.exists()
            and not self.workflow_commander_dir.is_dir()
        ):
            issues.append(
                f".workflow-commander exists but is not a directory: {self.workflow_commander_dir}"
            )

        # Check workflows directory (not required to exist)
        if self.workflows_dir.exists() and not self.workflows_dir.is_dir():
            issues.append(
                f"workflows directory exists but is not a directory: {self.workflows_dir}"
            )

        return len(issues) == 0, issues

    def __str__(self) -> str:
        """String representation of the configuration."""
        return f"ServerConfig(repository_path={self.repository_path}, enable_local_state_file={self.enable_local_state_file}, local_state_file_format={self.local_state_file_format})"

    def __repr__(self) -> str:
        """Detailed string representation of the configuration."""
        return f"ServerConfig(repository_path='{self.repository_path}', workflows_dir='{self.workflows_dir}')"
