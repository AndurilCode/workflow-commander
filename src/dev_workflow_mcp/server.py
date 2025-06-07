"""Main MCP server implementation."""

import argparse
import os
from pathlib import Path

from fastmcp import FastMCP

from .prompts.discovery_prompts import register_discovery_prompts
from .prompts.phase_prompts import register_phase_prompts
from .services.config_service import (
    ConfigurationService,
    EnvironmentConfiguration,
    PlatformConfiguration,
    ServerConfiguration,
    WorkflowConfiguration,
    initialize_configuration_service,
)
from .services.dependency_injection import register_singleton


def create_arg_parser() -> argparse.ArgumentParser:
    """Create and configure the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Development Workflow MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default repository path (current directory)
  %(prog)s
  
  # Run with specific repository path
  %(prog)s --repository-path /path/to/my/project
  
  # Enable local session file storage in markdown format
  %(prog)s --enable-local-state-file --local-state-file-format MD
  
  # Enable local session file storage in JSON format  
  %(prog)s --repository-path ../my-project --enable-local-state-file --local-state-file-format JSON
  
  # Enable cache mode for persistent workflow states
              %(prog)s --enable-cache-mode --cache-embedding-model all-MiniLM-L6-v2
  
  # Enable both file storage and cache mode
  %(prog)s --enable-local-state-file --enable-cache-mode --cache-db-path ./cache
""",
    )

    parser.add_argument(
        "--repository-path",
        type=str,
        help="Path to the repository root where .workflow-commander folder should be located. "
        "Defaults to current directory if not specified.",
        metavar="PATH",
    )

    parser.add_argument(
        "--enable-local-state-file",
        action="store_true",
        help="Enable automatic synchronization of workflow state to local files in "
        ".workflow-commander/sessions/ directory. When enabled, every workflow state "
        "change is automatically persisted to the filesystem.",
    )

    parser.add_argument(
        "--local-state-file-format",
        type=str,
        choices=["MD", "JSON", "md", "json"],
        default="MD",
        help="Format for local state files when --enable-local-state-file is enabled. "
        "Supports 'MD' for markdown or 'JSON' for structured JSON format. (default: %(default)s)",
        metavar="FORMAT",
    )

    parser.add_argument(
        "--session-retention-hours",
        type=int,
        default=168,  # 7 days
        help="Hours to keep completed sessions before cleanup. Minimum 1 hour. (default: %(default)s = 7 days)",
        metavar="HOURS",
    )

    parser.add_argument(
        "--disable-session-archiving",
        action="store_true",
        help="Disable archiving of session files before cleanup. By default, completed sessions "
        "are archived with a completion timestamp before being cleaned up.",
    )

    parser.add_argument(
        "--enable-cache-mode",
        action="store_true",
        help="Enable ChromaDB-based caching for workflow state persistence between sessions. "
        "When enabled, workflow states are stored in a vector database for semantic search and "
        "session restoration after MCP server restarts.",
    )

    parser.add_argument(
        "--cache-db-path",
        type=str,
        help="Path to ChromaDB database directory. If not specified, defaults to "
        ".workflow-commander/cache in the repository directory.",
        metavar="PATH",
    )

    parser.add_argument(
        "--cache-collection-name",
        type=str,
        default="workflow_states",
        help="Name of ChromaDB collection for workflow states. (default: %(default)s)",
        metavar="NAME",
    )

    parser.add_argument(
        "--cache-embedding-model",
        type=str,
        default="all-MiniLM-L6-v2",
        help="Sentence transformer model for semantic embeddings. (default: %(default)s)",
        metavar="MODEL",
    )

    parser.add_argument(
        "--cache-max-results",
        type=int,
        default=50,
        help="Maximum number of results for semantic search queries. (default: %(default)s)",
        metavar="COUNT",
    )

    return parser


def main():
    """Run the MCP server."""
    # Parse command-line arguments
    parser = create_arg_parser()
    args = parser.parse_args()

    # Create new configuration service
    try:
        # Create server configuration from CLI arguments
        server_config = ServerConfiguration(
            repository_path=Path(args.repository_path)
            if args.repository_path
            else Path.cwd(),
            enable_local_state_file=args.enable_local_state_file,
            local_state_file_format=args.local_state_file_format.upper(),
            session_retention_hours=args.session_retention_hours,
            enable_session_archiving=not args.disable_session_archiving,
            enable_cache_mode=args.enable_cache_mode,
            cache_db_path=args.cache_db_path,
            cache_collection_name=args.cache_collection_name,
            cache_embedding_model=args.cache_embedding_model,
            cache_max_results=args.cache_max_results,
        )

        # Create workflow configuration based on server settings
        workflow_config = WorkflowConfiguration(
            local_state_file=server_config.enable_local_state_file,
            local_state_file_format=server_config.local_state_file_format,
        )

        # Create platform configuration with detected settings
        platform_config = PlatformConfiguration(
            editor_type="cursor",  # This could be auto-detected from environment
            environment_variables=dict(os.environ),  # Pass through current environment
        )

        # Create environment configuration (auto-detects from environment)
        environment_config = EnvironmentConfiguration()

        # Initialize the configuration service
        config_service = initialize_configuration_service(
            server_config=server_config,
            workflow_config=workflow_config,
            platform_config=platform_config,
            environment_config=environment_config,
        )

        # Register configuration service in dependency injection container
        register_singleton(ConfigurationService, lambda: config_service)

        # Create legacy config for backward compatibility
        legacy_config = config_service.to_legacy_server_config()

    except Exception as e:
        print(f"Error: {e}")
        return 1

    # Initialize the MCP server
    mcp = FastMCP("Development Workflow")

    # Register essential YAML workflow prompts with configuration
    # Use legacy config for backward compatibility during migration
    register_phase_prompts(mcp, legacy_config)
    register_discovery_prompts(mcp, legacy_config)

    # Perform automatic cache restoration if cache mode is enabled
    if server_config.enable_cache_mode:
        try:
            from .utils.session_manager import auto_restore_sessions_on_startup

            restored_count = auto_restore_sessions_on_startup()
            if restored_count > 0:
                print(
                    f"Info: Automatically restored {restored_count} workflow session(s) from cache"
                )

        except Exception as e:
            # Non-blocking: don't let cache restoration prevent server startup
            print(f"Info: Automatic cache restoration skipped: {e}")

    # Run the server
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    exit(main())
