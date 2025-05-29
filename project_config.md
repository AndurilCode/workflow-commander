# Project Configuration

## Project Structure
- `src/dev_workflow_mcp/` - Main package source code
  - `server.py` - Main MCP server implementation
  - `models/` - Pydantic models for workflow state and responses
  - `prompts/` - Workflow prompt definitions organized by category
  - `utils/` - Utility functions for state management and validation
  - `templates/` - Template files for workflow and project configuration
- `tests/` - Test files (to be added)
- `docs/` - Documentation files
- `pyproject.toml` - Project configuration and dependencies
- `README.md` - Project documentation

## Dependencies
- Python 3.12+
- FastMCP - MCP server framework
- Pydantic - Data validation and settings management
- uv - Package and dependency management

## Test Commands
```bash
# Run tests (when implemented)
python -m pytest

# Run linter
ruff check .

# Format code
ruff format .

# Type checking
mypy src/

# Check all quality tools
ruff check . && ruff format --check . && mypy src/
```

## Build Commands
```bash
# Install dependencies
uv sync

# Install in development mode
uv pip install -e .

# Build package
python -m build

# Run the MCP server
python -m src.dev_workflow_mcp.server
```

## Changelog
- Added S3 synchronization capability for workflow states, enabling optional archival to Amazon S3 during workflow finalization with comprehensive error handling and graceful fallback
- Updated bootstrap-execute-tasks.sh to embed execute-tasks content directly instead of reading from external files, with Cursor receiving YAML frontmatter format while Copilot and Claude get clean content without YAML frontmatter
- Created bootstrap-execute-tasks.sh script that deploys execute-tasks guidelines to multiple AI assistants (Cursor, GitHub Copilot, Claude) with argument parsing, content checking, directory creation, and intelligent deployment logic
- Removed all utility tools (hello_workflow, get_session_statistics, health_check_sessions, export_client_session, cleanup_old_sessions) from MCP server to eliminate noise and provide a clean, focused tool interface for agents
- Fixed all 27 failing unit tests by adding Context parameters to test methods and updating test expectations for session-based state management
- Improved tool naming from `_prompt` to `_guidance` suffix to clearly indicate mandatory execution guidance that agents must follow exactly
- Implemented comprehensive unit test suite with 143 tests achieving 99% code coverage across all modules
- Implemented comprehensive workflow MCP server with phase-based prompts
- Added state management utilities and file templates
- Created prompt chaining system for guided workflow execution
- Added error recovery and validation prompts
- Implemented multi-item workflow processing capabilities 