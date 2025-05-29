"""Main MCP server implementation."""

import logging
import os

from fastmcp import FastMCP

from .models.config import S3Config
from .prompts.management_prompts import register_management_prompts
from .prompts.phase_prompts import register_phase_prompts
from .prompts.project_prompts import register_project_prompts
from .prompts.transition_prompts import register_transition_prompts
from .utils.session_manager import initialize_s3_client

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize the MCP server
mcp = FastMCP("Development Workflow")

# Register all workflow prompts
register_phase_prompts(mcp)
register_management_prompts(mcp)
register_transition_prompts(mcp)
register_project_prompts(mcp)


def main():
    """Run the MCP server."""
    # Initialize S3 client if configured
    s3_config = S3Config(
        enabled=os.getenv("S3_SYNC_ENABLED", "false").lower() == "true",
        bucket_name=os.getenv("S3_BUCKET_NAME"),
        region=os.getenv("AWS_REGION", "us-east-1"),
        prefix=os.getenv("S3_PREFIX", "workflow-states/"),
    )
    
    if s3_config.enabled and s3_config.bucket_name:
        initialize_s3_client(s3_config)
        logging.info(f"S3 sync enabled: {s3_config.bucket_name}")
    else:
        logging.info("S3 sync disabled")
    
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
