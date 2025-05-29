# S3 Synchronization Implementation Plan

## Step 1: Add S3 Dependencies
**File:** `pyproject.toml`
```diff
[tool.poetry.dependencies]
python = "^3.10"
mcp = "^1.3.5"
pydantic = "^2.10.4"
pytest = "^8.4.0"
pytest-asyncio = "^0.25.2"
+boto3 = "^1.35.0"
+botocore = "^1.35.0"
```

## Step 2: Create S3 Configuration Model
**File:** `src/dev_workflow_mcp/models/config.py` (NEW)
```python
class S3Config(BaseModel):
    """S3 configuration for workflow state synchronization."""
    enabled: bool = False
    bucket_name: Optional[str] = None
    prefix: str = "workflow-states/"
    region: str = "us-east-1"
    sync_on_finalize: bool = True
    archive_completed: bool = True
```

## Step 3: Create S3 Client Module
**File:** `src/dev_workflow_mcp/utils/s3_client.py` (NEW)
```python
class S3SyncClient:
    def __init__(self, config: S3Config)
    def sync_workflow_state(client_id: str, state_data: Dict) -> Optional[str]
    def generate_s3_key(client_id: str, timestamp: datetime) -> str
    def archive_completed_workflow(client_id: str, state_data: Dict) -> Optional[str]
```

## Step 4: Update Session Manager
**File:** `src/dev_workflow_mcp/utils/session_manager.py`
```diff
+from .s3_client import S3SyncClient, S3Config
+
+_s3_client: Optional[S3SyncClient] = None
+
+def initialize_s3_client(config: S3Config):
+    """Initialize S3 client for session synchronization."""
+    global _s3_client
+    _s3_client = S3SyncClient(config)
+
+def sync_session_to_s3(client_id: str, archive: bool = False) -> Optional[str]:
+    """Sync current session state to S3."""
+    if not _s3_client or not _s3_client.config.enabled:
+        return None
+    
+    session = get_session(client_id)
+    if not session:
+        return None
+    
+    state_dict = {
+        'client_id': session.client_id,
+        'phase': session.phase.value,
+        'status': session.status.value,
+        'current_item': session.current_item,
+        'items': [item.model_dump() for item in session.items],
+        'log': session.log,
+        'plan': session.plan,
+        'markdown_export': session.to_markdown()
+    }
+    
+    if archive and _s3_client.config.archive_completed:
+        return _s3_client.archive_completed_workflow(client_id, state_dict)
+    else:
+        return _s3_client.sync_workflow_state(client_id, state_dict)
```

## Step 5: Modify Finalize Workflow Guidance
**File:** `src/dev_workflow_mcp/prompts/management_prompts.py`
```diff
def finalize_workflow_guidance(context: Context) -> str:
    # ... existing code ...
    
+    # Sync to S3 if enabled
+    from ..utils.session_manager import sync_session_to_s3
+    s3_key = sync_session_to_s3(client_id, archive=True)
+    if s3_key:
+        add_log_to_session(client_id, f"[{timestamp}] 📤 Workflow archived to S3: {s3_key}")
    
    # Reset workflow state
    reset_session(client_id)
```

## Step 6: Add Server Configuration
**File:** `src/dev_workflow_mcp/server.py`
```diff
+import os
+from .models.config import S3Config
+from .utils.session_manager import initialize_s3_client

async def serve() -> None:
+    # Initialize S3 client if configured
+    s3_config = S3Config(
+        enabled=os.getenv("S3_SYNC_ENABLED", "false").lower() == "true",
+        bucket_name=os.getenv("S3_BUCKET_NAME"),
+        region=os.getenv("AWS_REGION", "us-east-1"),
+        prefix=os.getenv("S3_PREFIX", "workflow-states/")
+    )
+    
+    if s3_config.enabled and s3_config.bucket_name:
+        initialize_s3_client(s3_config)
+        logger.info(f"S3 sync enabled: {s3_config.bucket_name}")
```

## Step 7: Create S3 Tests
**File:** `tests/test_utils/test_s3_client.py` (NEW)
```python
@pytest.fixture
def mock_s3_client():
    with patch('boto3.client') as mock:
        yield mock

def test_sync_workflow_state(mock_s3_client):
    # Test successful sync
    # Test sync with disabled config
    # Test sync with S3 errors

def test_archive_completed_workflow(mock_s3_client):
    # Test archiving with proper key structure
    # Test metadata inclusion
```

## Step 8: Update Integration Tests
**File:** `tests/integration/test_workflow_integration.py`
```diff
+@patch('src.dev_workflow_mcp.utils.session_manager.sync_session_to_s3')
+def test_finalize_workflow_with_s3_sync(mock_sync):
+    # Test that finalization triggers S3 sync
+    # Verify archive flag is set to True
+    # Check log entry is added on successful sync
```

## Step 9: Update Documentation
**File:** `README.md`
```diff
+## S3 Integration
+
+The workflow commander supports optional S3 synchronization for workflow states.
+
+### Configuration
+Set the following environment variables:
+- `S3_SYNC_ENABLED=true` - Enable S3 synchronization
+- `S3_BUCKET_NAME=your-bucket` - S3 bucket for workflow states
+- `AWS_REGION=us-east-1` - AWS region (default: us-east-1)
+- `S3_PREFIX=workflow-states/` - S3 key prefix (default: workflow-states/)
+
+### Features
+- Automatic sync on workflow finalization
+- Archived workflows stored with timestamp
+- Graceful fallback if S3 is unavailable
```

## Execution Order
1. Add boto3 dependencies
2. Create config model
3. Implement S3 client
4. Update session manager
5. Modify finalize_workflow_guidance
6. Update server initialization
7. Write unit tests
8. Add integration tests
9. Update documentation

## Risk Mitigation
- S3 sync is opt-in (disabled by default)
- Graceful degradation if S3 fails
- No breaking changes to existing API
- Comprehensive error handling and logging