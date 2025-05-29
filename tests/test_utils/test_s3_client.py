"""Tests for S3 client functionality."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from src.dev_workflow_mcp.models.config import S3Config
from src.dev_workflow_mcp.utils.s3_client import S3SyncClient


@pytest.fixture
def s3_config():
    """Create test S3 configuration."""
    return S3Config(
        enabled=True,
        bucket_name="test-bucket",
        region="us-east-1",
        prefix="workflow-states/",
    )


@pytest.fixture
def s3_client(s3_config):
    """Create S3 client with test config."""
    return S3SyncClient(s3_config)


@pytest.fixture
def mock_boto3_client():
    """Mock boto3 S3 client."""
    with patch("boto3.client") as mock:
        yield mock


class TestS3SyncClient:
    """Test S3 sync client functionality."""

    def test_init(self, s3_config):
        """Test client initialization."""
        client = S3SyncClient(s3_config)
        assert client.config == s3_config
        assert client._client is None

    def test_lazy_client_init(self, s3_client, mock_boto3_client):
        """Test lazy initialization of boto3 client."""
        # Access client property
        _ = s3_client.client

        # Verify boto3.client was called
        mock_boto3_client.assert_called_once_with("s3", region_name="us-east-1")

    def test_client_init_no_credentials(self, s3_client, mock_boto3_client):
        """Test client initialization with no credentials."""
        mock_boto3_client.side_effect = NoCredentialsError()

        # Access client property
        client = s3_client.client

        # Verify config was disabled
        assert s3_client.config.enabled is False
        assert client is None

    def test_generate_s3_key_active(self, s3_client):
        """Test S3 key generation for active workflow."""
        key = s3_client.generate_s3_key("test-client")

        assert key.startswith("workflow-states/active/test-client/workflow_state.json")

    def test_generate_s3_key_archive(self, s3_client):
        """Test S3 key generation for archived workflow."""
        timestamp = datetime(2025, 5, 29, 13, 30, 45, tzinfo=UTC)
        key = s3_client.generate_s3_key(
            "test-client", timestamp=timestamp, archive=True
        )

        expected = (
            "workflow-states/archived/test-client/2025/05/29/133045_workflow_final.json"
        )
        assert key == expected

    def test_sync_workflow_state_success(self, s3_client, mock_boto3_client):
        """Test successful workflow state sync."""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        # Test data
        state_data = {
            "phase": "CONSTRUCT",
            "status": "RUNNING",
            "items": [],
        }

        # Sync state
        s3_key = s3_client.sync_workflow_state("test-client", state_data)

        # Verify S3 put_object was called
        assert s3_key is not None
        assert s3_key.startswith("workflow-states/active/test-client/")
        mock_s3.put_object.assert_called_once()

        # Verify call arguments
        call_args = mock_s3.put_object.call_args
        assert call_args.kwargs["Bucket"] == "test-bucket"
        assert call_args.kwargs["ContentType"] == "application/json"
        assert "_metadata" in call_args.kwargs["Body"]

    def test_sync_workflow_state_disabled(self, s3_config):
        """Test sync with disabled config."""
        s3_config.enabled = False
        client = S3SyncClient(s3_config)

        result = client.sync_workflow_state("test-client", {})
        assert result is None

    def test_sync_workflow_state_client_error(self, s3_client, mock_boto3_client):
        """Test sync with S3 client error."""
        # Mock S3 client to raise error
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied"}}, "PutObject"
        )
        mock_boto3_client.return_value = mock_s3

        # Sync state
        result = s3_client.sync_workflow_state("test-client", {})

        # Should return None on error
        assert result is None

    def test_archive_completed_workflow_success(self, s3_client, mock_boto3_client):
        """Test successful workflow archiving."""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        # Test data
        state_data = {
            "phase": "VALIDATE",
            "status": "COMPLETED",
            "items": [{"id": 1, "description": "Test task", "status": "completed"}],
        }

        # Archive workflow
        s3_key = s3_client.archive_completed_workflow("test-client", state_data)

        # Verify S3 put_object was called
        assert s3_key is not None
        assert "archived" in s3_key
        mock_s3.put_object.assert_called_once()

        # Verify metadata
        call_args = mock_s3.put_object.call_args
        assert call_args.kwargs["Metadata"]["archived"] == "true"
        assert call_args.kwargs["Metadata"]["workflow-status"] == "completed"

    def test_archive_completed_workflow_disabled(self, s3_config):
        """Test archiving with disabled archive config."""
        s3_config.archive_completed = False
        client = S3SyncClient(s3_config)

        result = client.archive_completed_workflow("test-client", {})
        assert result is None

    def test_retrieve_workflow_state_success(self, s3_client, mock_boto3_client):
        """Test successful workflow state retrieval."""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_response = {
            "Body": MagicMock(read=lambda: b'{"phase": "INIT", "status": "READY"}')
        }
        mock_s3.get_object.return_value = mock_response
        mock_boto3_client.return_value = mock_s3

        # Retrieve state
        result = s3_client.retrieve_workflow_state("test-key")

        # Verify result
        assert result is not None
        assert result["phase"] == "INIT"
        assert result["status"] == "READY"

    def test_retrieve_workflow_state_not_found(self, s3_client, mock_boto3_client):
        """Test retrieval with missing key."""
        # Mock S3 client to raise error
        mock_s3 = MagicMock()
        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}}, "GetObject"
        )
        mock_boto3_client.return_value = mock_s3

        # Retrieve state
        result = s3_client.retrieve_workflow_state("missing-key")

        # Should return None
        assert result is None

    def test_list_workflow_states_success(self, s3_client, mock_boto3_client):
        """Test listing workflow states."""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_response = {
            "Contents": [
                {"Key": "workflow-states/active/test-client/workflow_state.json"},
                {
                    "Key": "workflow-states/archived/test-client/2025/05/29/123456_workflow_final.json"
                },
                {"Key": "workflow-states/active/other-client/workflow_state.json"},
            ]
        }
        mock_s3.list_objects_v2.return_value = mock_response
        mock_boto3_client.return_value = mock_s3

        # List states
        result = s3_client.list_workflow_states("test-client", limit=5)

        # Verify result contains only test-client keys
        assert len(result) == 2
        assert all("test-client" in key for key in result)

    def test_list_workflow_states_empty(self, s3_client, mock_boto3_client):
        """Test listing with no results."""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": []}
        mock_boto3_client.return_value = mock_s3

        # List states
        result = s3_client.list_workflow_states("test-client")

        # Should return empty list
        assert result == []
