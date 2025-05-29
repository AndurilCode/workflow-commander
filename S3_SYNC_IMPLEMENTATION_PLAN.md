# S3 Synchronization Implementation Plan for Workflow Commander

## Overview
This document provides a detailed implementation plan for adding Amazon S3 synchronization capabilities to the workflow-commander MCP server. The synchronization will primarily occur during workflow finalization while maintaining the flexibility to extend to other state transitions.

## 1. Step-by-Step Implementation with File Changes

### Phase 1: Core S3 Functionality

#### 1.1 Create S3 Client Module
**File:** `src/dev_workflow_mcp/utils/s3_client.py`
```python
"""S3 client for workflow state synchronization."""

import json
import logging
from datetime import datetime, UTC
from typing import Optional, Dict, Any
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class S3Config(BaseModel):
    """S3 configuration settings."""
    bucket_name: str = Field(description="S3 bucket name")
    prefix: str = Field(default="workflow-states/", description="S3 key prefix")
    region: str = Field(default="us-east-1", description="AWS region")
    enabled: bool = Field(default=False, description="Enable S3 sync")
    sync_on_finalize: bool = Field(default=True, description="Sync on workflow finalization")
    sync_on_complete: bool = Field(default=False, description="Sync on item completion")
    archive_completed: bool = Field(default=True, description="Archive completed workflows")
    

class S3SyncClient:
    """Handles S3 synchronization for workflow states."""
    
    def __init__(self, config: S3Config):
        self.config = config
        self._client = None
        
    @property
    def client(self):
        """Lazy initialize S3 client."""
        if self._client is None and self.config.enabled:
            try:
                self._client = boto3.client('s3', region_name=self.config.region)
            except NoCredentialsError:
                logger.error("AWS credentials not found. S3 sync disabled.")
                self.config.enabled = False
        return self._client
    
    def generate_s3_key(self, client_id: str, timestamp: Optional[datetime] = None) -> str:
        """Generate S3 key for workflow state."""
        if timestamp is None:
            timestamp = datetime.now(UTC)
        
        date_str = timestamp.strftime("%Y/%m/%d")
        time_str = timestamp.strftime("%H%M%S")
        
        return f"{self.config.prefix}{date_str}/{client_id}/{time_str}_workflow_state.json"
    
    def sync_workflow_state(self, client_id: str, state_data: Dict[str, Any]) -> Optional[str]:
        """Sync workflow state to S3."""
        if not self.config.enabled or not self.client:
            return None
            
        try:
            # Add metadata
            state_data['_metadata'] = {
                'client_id': client_id,
                'synced_at': datetime.now(UTC).isoformat(),
                'version': '1.0'
            }
            
            # Generate S3 key
            s3_key = self.generate_s3_key(client_id)
            
            # Upload to S3
            self.client.put_object(
                Bucket=self.config.bucket_name,
                Key=s3_key,
                Body=json.dumps(state_data, indent=2),
                ContentType='application/json',
                Metadata={
                    'client-id': client_id,
                    'workflow-phase': state_data.get('phase', 'unknown'),
                    'workflow-status': state_data.get('status', 'unknown')
                }
            )
            
            logger.info(f"Successfully synced workflow state to S3: {s3_key}")
            return s3_key
            
        except ClientError as e:
            logger.error(f"Failed to sync to S3: {e}")
            return None
    
    def retrieve_workflow_state(self, s3_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve workflow state from S3."""
        if not self.config.enabled or not self.client:
            return None
            
        try:
            response = self.client.get_object(
                Bucket=self.config.bucket_name,
                Key=s3_key
            )
            
            state_data = json.loads(response['Body'].read())
            return state_data
            
        except ClientError as e:
            logger.error(f"Failed to retrieve from S3: {e}")
            return None
    
    def list_workflow_states(self, client_id: str, limit: int = 10) -> list[str]:
        """List recent workflow states for a client."""
        if not self.config.enabled or not self.client:
            return []
            
        try:
            prefix = f"{self.config.prefix}"
            response = self.client.list_objects_v2(
                Bucket=self.config.bucket_name,
                Prefix=prefix,
                MaxKeys=limit
            )
            
            keys = []
            for obj in response.get('Contents', []):
                if client_id in obj['Key']:
                    keys.append(obj['Key'])
            
            return sorted(keys, reverse=True)[:limit]
            
        except ClientError as e:
            logger.error(f"Failed to list S3 objects: {e}")
            return []
```

#### 1.2 Update Session Manager with S3 Integration
**File:** `src/dev_workflow_mcp/utils/session_manager.py` (additions)
```python
# Add imports
from .s3_client import S3SyncClient, S3Config
from typing import Optional

# Add after existing imports
_s3_client: Optional[S3SyncClient] = None

def initialize_s3_client(config: S3Config) -> None:
    """Initialize the S3 client with configuration."""
    global _s3_client
    _s3_client = S3SyncClient(config)

def sync_session_to_s3(client_id: str) -> Optional[str]:
    """Sync a session to S3."""
    if not _s3_client:
        return None
    
    session = get_session(client_id)
    if not session:
        return None
    
    # Convert session to dict for S3 storage
    state_dict = {
        'client_id': session.client_id,
        'created_at': session.created_at.isoformat(),
        'last_updated': session.last_updated.isoformat(),
        'phase': session.phase.value,
        'status': session.status.value,
        'current_item': session.current_item,
        'plan': session.plan,
        'items': [{'id': item.id, 'description': item.description, 'status': item.status} 
                  for item in session.items],
        'log': session.log,
        'archive_log': session.archive_log,
        'markdown_export': session.to_markdown()
    }
    
    return _s3_client.sync_workflow_state(client_id, state_dict)

def restore_session_from_s3(client_id: str, s3_key: str) -> bool:
    """Restore a session from S3."""
    if not _s3_client:
        return False
    
    state_data = _s3_client.retrieve_workflow_state(s3_key)
    if not state_data:
        return False
    
    try:
        # Reconstruct WorkflowState from S3 data
        items = [WorkflowItem(**item) for item in state_data.get('items', [])]
        
        state = WorkflowState(
            client_id=client_id,
            created_at=datetime.fromisoformat(state_data['created_at']),
            last_updated=datetime.fromisoformat(state_data['last_updated']),
            phase=WorkflowPhase(state_data['phase']),
            status=WorkflowStatus(state_data['status']),
            current_item=state_data.get('current_item'),
            plan=state_data.get('plan', ''),
            items=items,
            log=state_data.get('log', ''),
            archive_log=state_data.get('archive_log', '')
        )
        
        with session_lock:
            client_sessions[client_id] = state
        
        return True
    except Exception as e:
        logger.error(f"Failed to restore session from S3: {e}")
        return False
```

#### 1.3 Update Management Prompts for S3 Sync
**File:** `src/dev_workflow_mcp/prompts/management_prompts.py` (modifications)
```python
# Add import
from ..utils.session_manager import sync_session_to_s3

# Modify finalize_workflow_guidance function
@mcp.tool()
def finalize_workflow_guidance(ctx: Context) -> str:
    """Guide the agent to finalize the entire workflow with mandatory execution steps."""
    # Reset session to initial state
    client_id = ctx.client_id if ctx else "default"
    
    # Add final summary to log before archiving
    session = get_session(client_id)
    if session:
        completed_items = [item for item in session.items if item.status == "completed"]
        add_log_to_session(
            client_id, 
            f"🏁 WORKFLOW FINALIZED - {len(completed_items)} items completed successfully"
        )
    
    # Sync to S3 before resetting state
    s3_key = sync_session_to_s3(client_id)
    
    update_session_state(
        client_id=client_id,
        phase=WorkflowPhase.INIT,
        status=WorkflowStatus.READY,
        current_item=None
    )
    
    # Get final state to return
    updated_state = export_session_to_markdown(client_id)
    
    sync_message = ""
    if s3_key:
        sync_message = f"\n\n**☁️ S3 SYNC:**\n- Workflow archived to S3\n- Key: `{s3_key}`"
    
    return f"""🏁 WORKFLOW FINALIZED

**✅ STATE UPDATED AUTOMATICALLY:**
- Phase → INIT
- Status → READY
- CurrentItem → null
- Final summary logged and archived{sync_message}

**📋 FINAL WORKFLOW STATE:**
```markdown
{updated_state}
```

**🎉 WORKFLOW COMPLETE!**
- All items processed
- State reset for future workflows
- Session data preserved for reference

💫 **No further actions needed - workflow cycle complete!**
"""
```

### Phase 2: Configuration System

#### 2.1 Create Configuration Module
**File:** `src/dev_workflow_mcp/config.py`
```python
"""Configuration management for workflow commander."""

import os
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, ValidationError

from .utils.s3_client import S3Config


class WorkflowConfig(BaseModel):
    """Main configuration for workflow commander."""
    s3: S3Config = Field(default_factory=lambda: S3Config(enabled=False))
    log_level: str = Field(default="INFO", description="Logging level")
    session_cleanup_hours: int = Field(default=24, description="Hours to keep completed sessions")
    

def load_config_from_env() -> WorkflowConfig:
    """Load configuration from environment variables."""
    config_dict = {}
    
    # S3 configuration from environment
    if os.getenv('WORKFLOW_S3_ENABLED', '').lower() == 'true':
        config_dict['s3'] = {
            'enabled': True,
            'bucket_name': os.getenv('WORKFLOW_S3_BUCKET', ''),
            'prefix': os.getenv('WORKFLOW_S3_PREFIX', 'workflow-states/'),
            'region': os.getenv('WORKFLOW_S3_REGION', 'us-east-1'),
            'sync_on_finalize': os.getenv('WORKFLOW_S3_SYNC_ON_FINALIZE', 'true').lower() == 'true',
            'sync_on_complete': os.getenv('WORKFLOW_S3_SYNC_ON_COMPLETE', 'false').lower() == 'true',
            'archive_completed': os.getenv('WORKFLOW_S3_ARCHIVE_COMPLETED', 'true').lower() == 'true',
        }
    
    # Other configuration
    config_dict['log_level'] = os.getenv('WORKFLOW_LOG_LEVEL', 'INFO')
    config_dict['session_cleanup_hours'] = int(os.getenv('WORKFLOW_SESSION_CLEANUP_HOURS', '24'))
    
    return WorkflowConfig(**config_dict)


def load_config_from_file(file_path: Path) -> Optional[WorkflowConfig]:
    """Load configuration from JSON file."""
    if not file_path.exists():
        return None
    
    try:
        with open(file_path, 'r') as f:
            config_dict = json.load(f)
        return WorkflowConfig(**config_dict)
    except (json.JSONDecodeError, ValidationError) as e:
        print(f"Error loading config from {file_path}: {e}")
        return None


def load_config() -> WorkflowConfig:
    """Load configuration with precedence: file > env > defaults."""
    # First try config file
    config_file = Path.home() / '.workflow-commander' / 'config.json'
    file_config = load_config_from_file(config_file)
    
    if file_config:
        return file_config
    
    # Then try environment variables
    return load_config_from_env()
```

#### 2.2 Update Server Initialization
**File:** `src/dev_workflow_mcp/server.py` (modifications)
```python
# Add imports
import logging
from .config import load_config
from .utils.session_manager import initialize_s3_client

# Add after imports
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize configuration
config = load_config()
logging.getLogger().setLevel(config.log_level)

# Initialize S3 client if enabled
if config.s3.enabled:
    initialize_s3_client(config.s3)
    logger.info(f"S3 sync enabled for bucket: {config.s3.bucket_name}")
else:
    logger.info("S3 sync disabled")

# Rest of existing code...
```

### Phase 3: Error Handling & Recovery

#### 3.1 Create S3 Error Handler
**File:** `src/dev_workflow_mcp/utils/s3_error_handler.py`
```python
"""Error handling for S3 operations."""

import logging
from typing import Optional, Callable, Any
from functools import wraps
from botocore.exceptions import ClientError, NoCredentialsError, ConnectionError

logger = logging.getLogger(__name__)


class S3SyncError(Exception):
    """Base exception for S3 sync errors."""
    pass


class S3ConfigError(S3SyncError):
    """Configuration-related S3 errors."""
    pass


class S3NetworkError(S3SyncError):
    """Network-related S3 errors."""
    pass


def handle_s3_errors(fallback_return: Any = None):
    """Decorator to handle S3 errors gracefully."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except NoCredentialsError:
                logger.error(f"AWS credentials not configured for {func.__name__}")
                return fallback_return
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'NoSuchBucket':
                    logger.error(f"S3 bucket not found in {func.__name__}")
                elif error_code == 'AccessDenied':
                    logger.error(f"Access denied to S3 bucket in {func.__name__}")
                else:
                    logger.error(f"S3 client error in {func.__name__}: {e}")
                return fallback_return
            except ConnectionError:
                logger.error(f"Network error connecting to S3 in {func.__name__}")
                return fallback_return
            except Exception as e:
                logger.error(f"Unexpected error in {func.__name__}: {e}")
                return fallback_return
        return wrapper
    return decorator


class S3RetryPolicy:
    """Retry policy for S3 operations."""
    
    def __init__(self, max_retries: int = 3, backoff_factor: float = 2.0):
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
    
    def execute_with_retry(self, operation: Callable, *args, **kwargs):
        """Execute operation with retry logic."""
        import time
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return operation(*args, **kwargs)
            except (ConnectionError, ClientError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    sleep_time = self.backoff_factor ** attempt
                    logger.warning(f"S3 operation failed, retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"S3 operation failed after {self.max_retries} attempts")
        
        raise S3NetworkError(f"Operation failed after {self.max_retries} retries") from last_error
```

#### 3.2 Update S3 Client with Error Handling
**File:** `src/dev_workflow_mcp/utils/s3_client.py` (modifications)
```python
# Add imports
from .s3_error_handler import handle_s3_errors, S3RetryPolicy

# Update S3SyncClient class
class S3SyncClient:
    """Handles S3 synchronization for workflow states."""
    
    def __init__(self, config: S3Config):
        self.config = config
        self._client = None
        self.retry_policy = S3RetryPolicy()
    
    # ... existing code ...
    
    @handle_s3_errors(fallback_return=None)
    def sync_workflow_state(self, client_id: str, state_data: Dict[str, Any]) -> Optional[str]:
        """Sync workflow state to S3 with error handling."""
        if not self.config.enabled or not self.client:
            return None
        
        def _upload():
            # Add metadata
            state_data['_metadata'] = {
                'client_id': client_id,
                'synced_at': datetime.now(UTC).isoformat(),
                'version': '1.0'
            }
            
            # Generate S3 key
            s3_key = self.generate_s3_key(client_id)
            
            # Upload to S3
            self.client.put_object(
                Bucket=self.config.bucket_name,
                Key=s3_key,
                Body=json.dumps(state_data, indent=2),
                ContentType='application/json',
                Metadata={
                    'client-id': client_id,
                    'workflow-phase': state_data.get('phase', 'unknown'),
                    'workflow-status': state_data.get('status', 'unknown')
                }
            )
            
            return s3_key
        
        # Execute with retry
        s3_key = self.retry_policy.execute_with_retry(_upload)
        logger.info(f"Successfully synced workflow state to S3: {s3_key}")
        return s3_key
```

### Phase 4: Testing Implementation

#### 4.1 Unit Tests for S3 Client
**File:** `tests/test_utils/test_s3_client.py`
```python
"""Unit tests for S3 client functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, UTC
from botocore.exceptions import ClientError, NoCredentialsError

from src.dev_workflow_mcp.utils.s3_client import S3SyncClient, S3Config


class TestS3Config:
    """Test S3 configuration."""
    
    def test_default_config(self):
        """Test default S3 configuration."""
        config = S3Config(bucket_name="test-bucket")
        assert config.bucket_name == "test-bucket"
        assert config.prefix == "workflow-states/"
        assert config.region == "us-east-1"
        assert config.enabled is False
        assert config.sync_on_finalize is True
        assert config.sync_on_complete is False
        assert config.archive_completed is True
    
    def test_custom_config(self):
        """Test custom S3 configuration."""
        config = S3Config(
            bucket_name="custom-bucket",
            prefix="custom-prefix/",
            region="eu-west-1",
            enabled=True,
            sync_on_complete=True
        )
        assert config.bucket_name == "custom-bucket"
        assert config.prefix == "custom-prefix/"
        assert config.region == "eu-west-1"
        assert config.enabled is True
        assert config.sync_on_complete is True


class TestS3SyncClient:
    """Test S3 sync client."""
    
    def setup_method(self):
        """Set up test client."""
        self.config = S3Config(bucket_name="test-bucket", enabled=True)
        self.client = S3SyncClient(self.config)
    
    @patch('boto3.client')
    def test_client_initialization(self, mock_boto_client):
        """Test S3 client initialization."""
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        
        # Access client property
        s3_client = self.client.client
        
        mock_boto_client.assert_called_once_with('s3', region_name='us-east-1')
        assert s3_client == mock_s3
    
    @patch('boto3.client')
    def test_client_initialization_no_credentials(self, mock_boto_client):
        """Test S3 client initialization with no credentials."""
        mock_boto_client.side_effect = NoCredentialsError()
        
        # Access client property
        s3_client = self.client.client
        
        assert s3_client is None
        assert self.config.enabled is False
    
    def test_generate_s3_key(self):
        """Test S3 key generation."""
        test_time = datetime(2024, 1, 15, 10, 30, 45, tzinfo=UTC)
        key = self.client.generate_s3_key("test-client", test_time)
        
        expected_key = "workflow-states/2024/01/15/test-client/103045_workflow_state.json"
        assert key == expected_key
    
    def test_generate_s3_key_current_time(self):
        """Test S3 key generation with current time."""
        key = self.client.generate_s3_key("test-client")
        
        assert key.startswith("workflow-states/")
        assert "test-client" in key
        assert key.endswith("_workflow_state.json")
    
    @patch('boto3.client')
    def test_sync_workflow_state_success(self, mock_boto_client):
        """Test successful workflow state sync."""
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        
        state_data = {
            'phase': 'VALIDATE',
            'status': 'COMPLETED',
            'items': []
        }
        
        s3_key = self.client.sync_workflow_state("test-client", state_data)
        
        assert s3_key is not None
        assert "test-client" in s3_key
        mock_s3.put_object.assert_called_once()
        
        # Verify put_object call
        call_args = mock_s3.put_object.call_args
        assert call_args.kwargs['Bucket'] == 'test-bucket'
        assert 'workflow_state.json' in call_args.kwargs['Key']
        assert call_args.kwargs['ContentType'] == 'application/json'
    
    @patch('boto3.client')
    def test_sync_workflow_state_disabled(self, mock_boto_client):
        """Test workflow state sync when disabled."""
        self.config.enabled = False
        
        result = self.client.sync_workflow_state("test-client", {})
        
        assert result is None
        mock_boto_client.assert_not_called()
    
    @patch('boto3.client')
    def test_sync_workflow_state_error(self, mock_boto_client):
        """Test workflow state sync with S3 error."""
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        mock_s3.put_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchBucket'}}, 'PutObject'
        )
        
        result = self.client.sync_workflow_state("test-client", {})
        
        assert result is None
    
    @patch('boto3.client')
    def test_retrieve_workflow_state_success(self, mock_boto_client):
        """Test successful workflow state retrieval."""
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        
        mock_response = {
            'Body': MagicMock(read=lambda: b'{"phase": "VALIDATE", "status": "COMPLETED"}')
        }
        mock_s3.get_object.return_value = mock_response
        
        result = self.client.retrieve_workflow_state("test-key")
        
        assert result is not None
        assert result['phase'] == 'VALIDATE'
        assert result['status'] == 'COMPLETED'
    
    @patch('boto3.client')
    def test_list_workflow_states(self, mock_boto_client):
        """Test listing workflow states."""
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        
        mock_response = {
            'Contents': [
                {'Key': 'workflow-states/2024/01/15/test-client/103045_workflow_state.json'},
                {'Key': 'workflow-states/2024/01/14/test-client/153045_workflow_state.json'},
                {'Key': 'workflow-states/2024/01/13/other-client/183045_workflow_state.json'},
            ]
        }
        mock_s3.list_objects_v2.return_value = mock_response
        
        result = self.client.list_workflow_states("test-client", limit=5)
        
        assert len(result) == 2
        assert all("test-client" in key for key in result)
        assert result[0] > result[1]  # Should be sorted in reverse order
```

#### 4.2 Integration Tests
**File:** `tests/integration/test_s3_integration.py`
```python
"""Integration tests for S3 functionality."""

import pytest
from unittest.mock import patch, Mock
from datetime import datetime, UTC

from src.dev_workflow_mcp.utils.s3_client import S3Config
from src.dev_workflow_mcp.utils.session_manager import (
    initialize_s3_client,
    sync_session_to_s3,
    restore_session_from_s3,
    create_session,
    get_session,
    client_sessions
)
from src.dev_workflow_mcp.utils.state_manager import StateManager


class TestS3Integration:
    """Test S3 integration with session management."""
    
    def setup_method(self):
        """Clear sessions and reset S3 client."""
        client_sessions.clear()
        initialize_s3_client(S3Config(bucket_name="test-bucket", enabled=False))
    
    @patch('boto3.client')
    def test_workflow_finalization_with_s3_sync(self, mock_boto_client):
        """Test workflow finalization triggers S3 sync."""
        # Setup S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        mock_s3.put_object.return_value = {}
        
        # Initialize S3 with sync enabled
        s3_config = S3Config(
            bucket_name="test-bucket",
            enabled=True,
            sync_on_finalize=True
        )
        initialize_s3_client(s3_config)
        
        # Create and complete a workflow
        state_manager = StateManager(client_id="test-s3-client")
        state_manager.create_initial_state("S3 sync test task")
        state_manager.update_state_section("VALIDATE", "COMPLETED")
        
        # Sync to S3
        s3_key = sync_session_to_s3("test-s3-client")
        
        assert s3_key is not None
        assert "test-s3-client" in s3_key
        mock_s3.put_object.assert_called_once()
    
    @patch('boto3.client')
    def test_restore_session_from_s3(self, mock_boto_client):
        """Test restoring a session from S3."""
        # Setup S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        
        # Mock S3 response
        s3_data = {
            'client_id': 'restored-client',
            'created_at': datetime.now(UTC).isoformat(),
            'last_updated': datetime.now(UTC).isoformat(),
            'phase': 'VALIDATE',
            'status': 'COMPLETED',
            'current_item': None,
            'plan': 'Test plan',
            'items': [
                {'id': 1, 'description': 'Test item', 'status': 'completed'}
            ],
            'log': 'Test log',
            'archive_log': 'Test archive'
        }
        
        mock_response = {
            'Body': Mock(read=lambda: json.dumps(s3_data).encode())
        }
        mock_s3.get_object.return_value = mock_response
        
        # Initialize S3
        s3_config = S3Config(bucket_name="test-bucket", enabled=True)
        initialize_s3_client(s3_config)
        
        # Restore session
        success = restore_session_from_s3('restored-client', 'test-key')
        
        assert success is True
        
        # Verify session was restored
        session = get_session('restored-client')
        assert session is not None
        assert session.phase.value == 'VALIDATE'
        assert session.status.value == 'COMPLETED'
        assert len(session.items) == 1
        assert session.items[0].description == 'Test item'
    
    def test_s3_sync_disabled_by_default(self):
        """Test that S3 sync is disabled by default."""
        # Create workflow without S3 configuration
        state_manager = StateManager(client_id="no-s3-client")
        state_manager.create_initial_state("No S3 sync task")
        
        # Attempt sync
        result = sync_session_to_s3("no-s3-client")
        
        assert result is None
```

### Phase 5: Documentation and Configuration Examples

#### 5.1 Environment Variables Documentation
**File:** `docs/S3_CONFIGURATION.md`
```markdown
# S3 Configuration Guide

## Environment Variables

Configure S3 synchronization using the following environment variables:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `WORKFLOW_S3_ENABLED` | Enable S3 synchronization | `false` | No |
| `WORKFLOW_S3_BUCKET` | S3 bucket name | - | Yes (if enabled) |
| `WORKFLOW_S3_PREFIX` | S3 key prefix | `workflow-states/` | No |
| `WORKFLOW_S3_REGION` | AWS region | `us-east-1` | No |
| `WORKFLOW_S3_SYNC_ON_FINALIZE` | Sync on workflow finalization | `true` | No |
| `WORKFLOW_S3_SYNC_ON_COMPLETE` | Sync on item completion | `false` | No |
| `WORKFLOW_S3_ARCHIVE_COMPLETED` | Archive completed workflows | `true` | No |

## AWS Credentials

The S3 client uses the standard AWS SDK credential chain:

1. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
2. AWS credentials file (`~/.aws/credentials`)
3. IAM role (for EC2/ECS/Lambda)

## Configuration File

Alternatively, create a configuration file at `~/.workflow-commander/config.json`:

```json
{
  "s3": {
    "enabled": true,
    "bucket_name": "my-workflow-bucket",
    "prefix": "workflows/",
    "region": "us-west-2",
    "sync_on_finalize": true,
    "sync_on_complete": false,
    "archive_completed": true
  },
  "log_level": "INFO",
  "session_cleanup_hours": 24
}
```

## IAM Policy

Required S3 permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-bucket-name/*",
        "arn:aws:s3:::your-bucket-name"
      ]
    }
  ]
}
```
```

#### 5.2 Usage Examples
**File:** `examples/s3_sync_example.sh`
```bash
#!/bin/bash

# Example 1: Basic S3 sync enabled
export WORKFLOW_S3_ENABLED=true
export WORKFLOW_S3_BUCKET=my-workflow-states
export AWS_PROFILE=my-profile

# Run workflow commander
dev-workflow-mcp

# Example 2: Custom configuration
export WORKFLOW_S3_ENABLED=true
export WORKFLOW_S3_BUCKET=company-workflows
export WORKFLOW_S3_PREFIX=team/project/
export WORKFLOW_S3_REGION=eu-west-1
export WORKFLOW_S3_SYNC_ON_COMPLETE=true

# Example 3: Using configuration file
cat > ~/.workflow-commander/config.json << EOF
{
  "s3": {
    "enabled": true,
    "bucket_name": "workflow-archives",
    "prefix": "production/",
    "region": "us-east-1",
    "sync_on_finalize": true,
    "sync_on_complete": true,
    "archive_completed": true
  }
}
EOF

dev-workflow-mcp
```

### Phase 6: Update Dependencies

#### 6.1 Update pyproject.toml
**File:** `pyproject.toml` (modifications)
```toml
[project]
name = "dev-workflow-mcp"
version = "0.2.0"  # Bump version
description = "Development workflow MCP server with S3 synchronization"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastmcp",
    "pydantic",
    "boto3>=1.28.0",  # Add boto3 for S3
]

[project.optional-dependencies]
dev = [
    "ruff",
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "pytest-mock>=3.10.0",
    "moto>=4.2.0",  # Add moto for S3 mocking in tests
]
```

## 2. Configuration Approach for S3 Credentials

### Hierarchical Configuration
1. **Configuration file** (`~/.workflow-commander/config.json`) - highest priority
2. **Environment variables** - medium priority
3. **Default values** - lowest priority

### AWS Credential Chain
- Standard AWS SDK credential resolution
- Support for IAM roles, credentials file, and environment variables
- No credentials stored in code

### Security Considerations
- Never log credentials
- Use IAM roles in production
- Implement least-privilege S3 bucket policies
- Consider encryption at rest and in transit

## 3. Error Handling Strategy

### Graceful Degradation
- S3 sync failures don't block workflow execution
- Errors are logged but workflow continues
- Failed syncs can be retried manually

### Retry Logic
- Exponential backoff for transient failures
- Maximum 3 retries by default
- Network errors trigger automatic retry

### Error Types
1. **Configuration errors** - Disable S3 sync
2. **Authentication errors** - Log and disable
3. **Network errors** - Retry with backoff
4. **Permission errors** - Log detailed error

## 4. Testing Approach

### Unit Tests
- Mock boto3 client
- Test all S3 operations
- Test error scenarios
- Verify retry logic

### Integration Tests
- Use moto for S3 mocking
- Test full workflow with S3 sync
- Test session restoration
- Verify error handling

### Manual Testing Checklist
1. Test with real S3 bucket
2. Test with invalid credentials
3. Test network interruption
4. Test large workflow states
5. Test concurrent workflows

## 5. Backward Compatibility Considerations

### No Breaking Changes
- S3 sync is opt-in (disabled by default)
- Existing workflows continue unchanged
- Session-based architecture preserved
- No changes to existing APIs

### Migration Path
1. Existing users update with no changes required
2. Enable S3 sync via configuration when ready
3. Historical data can be manually synced

### Future Extensions
- Sync on other state transitions (already supported via config)
- Bulk export/import tools
- S3 lifecycle policies for archival
- Cross-region replication support

## Implementation Timeline

1. **Phase 1** (2-3 days): Core S3 functionality
2. **Phase 2** (1-2 days): Configuration system
3. **Phase 3** (1-2 days): Error handling
4. **Phase 4** (2-3 days): Testing
5. **Phase 5** (1 day): Documentation
6. **Phase 6** (1 day): Release preparation

Total estimated time: 8-12 days

## Risk Mitigation

1. **S3 costs** - Implement lifecycle policies
2. **Large states** - Consider compression
3. **Network latency** - Async sync option for future
4. **Credential exposure** - Use IAM roles and audit logs