"""Workflow cache manager using ChromaDB for persistent storage and semantic search."""

import contextlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import chromadb
from chromadb.config import Settings

# Lazy import for SentenceTransformer to avoid heavy startup loading
if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer
else:
    SentenceTransformer = object  # Type placeholder for runtime

from ..models.cache_models import (
    CacheMetadata,
    CacheOperationResult,
    CacheSearchQuery,
    CacheStats,
    SemanticSearchResult,
)
from ..models.workflow_state import DynamicWorkflowState


class WorkflowCacheManager:
    """Manages workflow state caching using ChromaDB with semantic search capabilities."""

    def __init__(
        self,
        db_path: str,
        collection_name: str = "workflow_states",
        embedding_model: str = "all-MiniLM-L6-v2",
        max_results: int = 50,
    ):
        """Initialize the cache manager.

        Args:
            db_path: Path to ChromaDB database directory
            collection_name: Name of the ChromaDB collection
            embedding_model: Sentence transformer model for embeddings
            max_results: Maximum results for search queries
        """
        self.db_path = Path(db_path)
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model
        self.max_results = max_results
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Lazy initialization for expensive operations
        self._client: chromadb.Client | None = None
        self._collection: chromadb.Collection | None = None
        self._embedding_model: SentenceTransformer | None = None
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Ensure the cache manager is initialized.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        if self._initialized:
            return True
            
        with self._lock:
            if self._initialized:
                return True
                
            try:
                # Ensure database directory exists
                self.db_path.mkdir(parents=True, exist_ok=True)
                
                # Initialize ChromaDB client
                self._client = chromadb.PersistentClient(
                    path=str(self.db_path),
                    settings=Settings(
                        anonymized_telemetry=False,
                        allow_reset=True
                    )
                )
                
                # Get or create collection
                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"description": "Workflow states with semantic embeddings"}
                )
                
                # Initialize embedding model (lazy loading for performance)
                # Model will be loaded on first use
                
                self._initialized = True
                return True
                
            except Exception as e:
                # Log error but don't raise to avoid breaking workflow execution
                print(f"Warning: Failed to initialize cache manager: {e}")
                return False

    def _is_test_environment(self) -> bool:
        """Detect if we're running in a test environment.
        
        Returns:
            True if running in tests, False otherwise
        """
        import sys
        
        # Check for pytest in sys.modules
        if 'pytest' in sys.modules:
            return True
            
        # Check for common test environment variables
        import os
        test_indicators = [
            'PYTEST_CURRENT_TEST',
            'CI',
            'GITHUB_ACTIONS',
            '_called_from_test'
        ]
        
        for indicator in test_indicators:
            if os.environ.get(indicator):
                return True
                
        # Check for test in command line arguments
        return any('test' in arg.lower() for arg in sys.argv)

    def _create_mock_model(self) -> object:
        """Create a mock embedding model for test environments.
        
        Returns:
            Mock object that provides encode() method with dummy embeddings
        """
        class MockEmbeddingModel:
            """Mock embedding model for testing."""
            
            def encode(self, texts, **kwargs):
                """Generate dummy embeddings for testing."""
                import numpy as np
                
                if isinstance(texts, str):
                    texts = [texts]
                    
                # Generate consistent dummy embeddings (384 dimensions like MiniLM)
                embeddings = []
                for _i, text in enumerate(texts):
                    # Use hash of text for consistency
                    seed = hash(text) % (2**32)
                    np.random.seed(seed)
                    embedding = np.random.normal(0, 1, 384).astype(np.float32)
                    # Normalize like real embeddings
                    embedding = embedding / np.linalg.norm(embedding)
                    embeddings.append(embedding)
                    
                return np.array(embeddings)
                
        return MockEmbeddingModel()

    def _get_embedding_model(self) -> SentenceTransformer | None:
        """Get the embedding model, loading it if necessary.
        
        In test environments, returns a mock object to avoid heavy loading.
        Otherwise uses a fallback chain for model selection:
        1. Configured model (self.embedding_model_name)
        2. all-MiniLM-L6-v2 (fast, good quality)
        3. all-mpnet-base-v2 (slower, high quality)
        
        Returns:
            SentenceTransformer model or None if loading fails
        """
        if self._embedding_model is not None:
            return self._embedding_model
            
        # Skip heavy model loading in test environments
        if self._is_test_environment():
            print("Test environment detected: using mock embedding model")
            self._embedding_model = self._create_mock_model()
            return self._embedding_model
            
        try:
            # Lazy import SentenceTransformer only when actually needed
            from sentence_transformers import SentenceTransformer
            
            # Define fallback model chain (fast → high quality)
            model_chain = [
                self.embedding_model_name,  # User-configured model
                "all-MiniLM-L6-v2",         # Fast default (91MB)
                "all-mpnet-base-v2",        # High quality fallback (335MB)
            ]
            
            # Remove duplicates while preserving order
            model_chain = list(dict.fromkeys(model_chain))
            
            for model_name in model_chain:
                try:
                    print(f"Loading embedding model: {model_name}")
                    self._embedding_model = SentenceTransformer(model_name)
                    if model_name != self.embedding_model_name:
                        print(f"Note: Using fallback model {model_name} instead of {self.embedding_model_name}")
                    return self._embedding_model
                except Exception as e:
                    print(f"Warning: Failed to load model {model_name}: {e}")
                    continue
                    
            # All models failed
            print("Error: All embedding models failed to load")
            return None
            
        except ImportError as e:
            print(f"Warning: sentence-transformers not available: {e}")
            return None

    def _generate_embedding_text(self, state: DynamicWorkflowState) -> str:
        """Generate text for embedding from workflow state.
        
        Enhanced to include rich semantic content from node outputs for better similarity matching.
        
        Args:
            state: Workflow state to generate text from
            
        Returns:
            str: Text suitable for embedding generation with rich semantic content
        """
        # Combine key state information for semantic search
        text_parts = [
            f"Workflow: {state.workflow_name}",
            f"Current node: {state.current_node}",
            f"Status: {state.status}",
        ]
        
        # Add current item if available
        if state.current_item:
            text_parts.append(f"Current task: {state.current_item}")
            
        # Add recent log entries (last 5 for more context)
        if state.log:
            recent_logs = state.log[-5:]
            text_parts.append(f"Recent activity: {' '.join(recent_logs)}")
            
        # Add execution context if available
        if state.execution_context:
            context_summary = ', '.join(f"{k}: {v}" for k, v in state.execution_context.items())
            text_parts.append(f"Context: {context_summary}")
            
        # Enhanced node outputs processing for semantic richness
        if state.node_outputs:
            semantic_content = []
            detailed_work = []
            
            for node_name, outputs in state.node_outputs.items():
                # Extract completed criteria details for semantic search
                if "completed_criteria" in outputs and isinstance(outputs["completed_criteria"], dict):
                    criteria_content = []
                    for criterion_name, criterion_evidence in outputs["completed_criteria"].items():
                        # Include both criterion name and detailed evidence
                        criteria_content.append(f"{criterion_name}: {criterion_evidence}")
                    
                    if criteria_content:
                        semantic_content.append(f"Node {node_name} completed work: {' | '.join(criteria_content)}")
                
                # Include other output types that provide semantic value
                for key, value in outputs.items():
                    if key != "completed_criteria" and isinstance(value, str) and len(value) > 10:
                        # Include substantial text content that adds semantic value
                        detailed_work.append(f"{node_name} {key}: {value}")
            
            # Add semantic content (high priority for embeddings)
            if semantic_content:
                text_parts.extend(semantic_content)
            
            # Add other detailed work content
            if detailed_work:
                text_parts.append(f"Additional work details: {' | '.join(detailed_work[:3])}")  # Limit to prevent bloat
            
            # Fallback to original format if no rich content available
            if not semantic_content and not detailed_work:
                outputs_summary = []
                for node_name, outputs in state.node_outputs.items():
                    node_parts = [f"Node {node_name}"]
                    for key, value in outputs.items():
                        if isinstance(value, dict):
                            value = ', '.join(f"{k}: {v}" for k, v in value.items())
                        node_parts.append(f"{key}: {value}")
                    outputs_summary.append(' - '.join(node_parts))
                text_parts.append(f"Completed outputs: {' | '.join(outputs_summary)}")
            
        return " | ".join(text_parts)

    def store_workflow_state(self, state: DynamicWorkflowState) -> CacheOperationResult:
        """Store a workflow state in the cache.
        
        Args:
            state: Workflow state to store
            
        Returns:
            CacheOperationResult: Result of the store operation
        """
        if not self._ensure_initialized():
            return CacheOperationResult(
                success=False,
                error_message="Cache manager not initialized",
                operation_type="store"
            )
            
        try:
            with self._lock:
                # Generate embedding text
                embedding_text = self._generate_embedding_text(state)
                
                # Create metadata
                metadata = CacheMetadata(
                    session_id=state.session_id,
                    client_id=state.client_id,
                    workflow_name=state.workflow_name,
                    workflow_file=state.workflow_file,
                    current_node=state.current_node,
                    current_item=state.current_item,
                    status=state.status,
                    node_outputs=state.node_outputs,
                    created_at=state.created_at,
                    last_updated=state.last_updated,
                )
                
                # Create cached state (metadata for storage)
                
                # Generate embedding
                model = self._get_embedding_model()
                if model is None:
                    return CacheOperationResult(
                        success=False,
                        error_message="Embedding model not available",
                        operation_type="store"
                    )
                    
                embedding = model.encode([embedding_text])[0].tolist()
                
                # Serialize metadata for ChromaDB (convert datetime to string and serialize complex objects)
                metadata_dict = metadata.model_dump()
                for key, value in metadata_dict.items():
                    if isinstance(value, datetime):
                        metadata_dict[key] = value.isoformat()
                    elif isinstance(value, dict):
                        # Serialize complex dictionaries like node_outputs to JSON string
                        metadata_dict[key] = json.dumps(value) if value else "{}"
                
                # Store in ChromaDB
                self._collection.upsert(
                    ids=[state.session_id],
                    embeddings=[embedding],
                    documents=[embedding_text],
                    metadatas=[metadata_dict]
                )
                
                return CacheOperationResult(
                    success=True,
                    session_id=state.session_id,
                    operation_type="store"
                )
                
        except Exception as e:
            return CacheOperationResult(
                success=False,
                error_message=str(e),
                operation_type="store"
            )

    def retrieve_workflow_state(self, session_id: str) -> DynamicWorkflowState | None:
        """Retrieve a workflow state from the cache.
        
        Args:
            session_id: Session ID to retrieve
            
        Returns:
            DynamicWorkflowState or None if not found
        """
        if not self._ensure_initialized():
            return None
            
        try:
            with self._lock:
                # Query ChromaDB for the specific session
                results = self._collection.get(
                    ids=[session_id],
                    include=["metadatas", "documents"]
                )
                
                if not results["ids"] or len(results["ids"]) == 0:
                    return None
                    
                # Get metadata and deserialize datetime strings
                metadata_dict = results["metadatas"][0]
                
                # Convert ISO datetime strings back to datetime objects and deserialize JSON
                for key, value in metadata_dict.items():
                    if isinstance(value, str) and (key.endswith('_at') or key.endswith('_time') or key.endswith('_updated')):
                        with contextlib.suppress(ValueError, TypeError):
                            dt = datetime.fromisoformat(value)
                            # Ensure timezone awareness - if naive, assume UTC
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=UTC)
                            metadata_dict[key] = dt
                    elif isinstance(value, str) and key == 'node_outputs':
                        # Deserialize node_outputs JSON string back to dict
                        try:
                            metadata_dict[key] = json.loads(value) if value else {}
                        except (ValueError, TypeError, json.JSONDecodeError):
                            # If JSON parsing fails, use empty dict as fallback
                            metadata_dict[key] = {}
                
                metadata = CacheMetadata(**metadata_dict)
                
                # Note: We don't store the full state data in ChromaDB for this initial version
                # Instead, we create a minimal state from metadata for persistence restoration
                # Full state reconstruction would require storing state_data in ChromaDB
                
                # Create a minimal workflow state from metadata
                state = DynamicWorkflowState(
                    session_id=metadata.session_id,
                    client_id=metadata.client_id,
                    workflow_name=metadata.workflow_name,
                    workflow_file=metadata.workflow_file,
                    current_node=metadata.current_node,
                    current_item=metadata.current_item,
                    status=metadata.status,
                    node_outputs=metadata.node_outputs,
                    created_at=metadata.created_at,
                    last_updated=metadata.last_updated,
                )
                
                return state
                
        except Exception as e:
            print(f"Warning: Failed to retrieve workflow state {session_id}: {e}")
            return None

    def delete_workflow_state(self, session_id: str) -> CacheOperationResult:
        """Delete a workflow state from the cache.
        
        Args:
            session_id: Session ID to delete
            
        Returns:
            CacheOperationResult: Result of the delete operation
        """
        if not self._ensure_initialized():
            return CacheOperationResult(
                success=False,
                error_message="Cache manager not initialized",
                operation_type="delete"
            )
            
        try:
            with self._lock:
                self._collection.delete(ids=[session_id])
                
                return CacheOperationResult(
                    success=True,
                    session_id=session_id,
                    operation_type="delete"
                )
                
        except Exception as e:
            return CacheOperationResult(
                success=False,
                error_message=str(e),
                operation_type="delete"
            )

    def get_cache_stats(self) -> CacheStats | None:
        """Get statistics about the cache.
        
        Returns:
            CacheStats or None if unavailable
        """
        if not self._ensure_initialized():
            return None
            
        try:
            with self._lock:
                # Get all entries
                results = self._collection.get(include=["metadatas"])
                
                if not results["metadatas"]:
                    return CacheStats(
                        total_entries=0,
                        active_sessions=0,
                        completed_sessions=0,
                        cache_size_mb=0.0,
                        collection_name=self.collection_name
                    )
                
                # Convert ISO datetime strings back to datetime objects and deserialize JSON for each metadata
                metadatas = []
                for m in results["metadatas"]:
                    metadata_dict = dict(m)
                    for key, value in metadata_dict.items():
                        if isinstance(value, str) and (key.endswith('_at') or key.endswith('_time') or key.endswith('_updated')):
                            with contextlib.suppress(ValueError, TypeError):
                                dt = datetime.fromisoformat(value)
                                # Ensure timezone awareness - if naive, assume UTC
                                if dt.tzinfo is None:
                                    dt = dt.replace(tzinfo=UTC)
                                metadata_dict[key] = dt
                        elif isinstance(value, str) and key == 'node_outputs':
                            # Deserialize node_outputs JSON string back to dict
                            try:
                                metadata_dict[key] = json.loads(value) if value else {}
                            except (ValueError, TypeError, json.JSONDecodeError):
                                # If JSON parsing fails, use empty dict as fallback
                                metadata_dict[key] = {}
                    metadatas.append(CacheMetadata(**metadata_dict))
                
                # Calculate statistics
                total_entries = len(metadatas)
                active_sessions = sum(1 for m in metadatas if m.status not in ["COMPLETED", "ERROR", "FINISHED"])
                completed_sessions = total_entries - active_sessions
                
                # Calculate timestamps
                timestamps = [m.cache_created_at for m in metadatas]
                oldest_entry = min(timestamps) if timestamps else None
                newest_entry = max(timestamps) if timestamps else None
                
                # Estimate cache size (rough approximation)
                cache_size_mb = len(json.dumps(results["metadatas"])) / (1024 * 1024)
                
                return CacheStats(
                    total_entries=total_entries,
                    active_sessions=active_sessions,
                    completed_sessions=completed_sessions,
                    oldest_entry=oldest_entry,
                    newest_entry=newest_entry,
                    cache_size_mb=round(cache_size_mb, 2),
                    collection_name=self.collection_name
                )
                
        except Exception as e:
            print(f"Warning: Failed to get cache stats: {e}")
            return None

    def is_available(self) -> bool:
        """Check if the cache is available for use.
        
        Returns:
            bool: True if cache is available
        """
        return self._ensure_initialized()

    def semantic_search(
        self, 
        search_text: str = None,
        query: CacheSearchQuery = None,
        client_id: str = None,
        workflow_name: str = None,
        status_filter: list[str] = None,
        min_similarity: float = 0.1,
        max_results: int = 50,
        include_inactive: bool = True
    ) -> list[SemanticSearchResult]:
        """Perform semantic search on cached workflow states.
        
        Args:
            search_text: Text to search for (alternative to query object)
            query: Search query object (alternative to individual parameters)
            client_id: Filter by client ID
            workflow_name: Filter by workflow name
            status_filter: Filter by status values
            min_similarity: Minimum similarity score
            max_results: Maximum number of results
            include_inactive: Include inactive/completed sessions
            
        Returns:
            List of semantic search results ordered by similarity
        """
        if not self._ensure_initialized():
            return []
        
        # Handle both calling styles
        if query is not None:
            # Use query object
            search_text = query.search_text
            client_id = query.client_id
            workflow_name = query.workflow_name
            status_filter = query.status_filter
            min_similarity = query.min_similarity
            max_results = query.max_results
            # include_inactive = query.include_inactive  # Future use
        elif search_text is None:
            # No search text provided
            return []
            
        try:
            with self._lock:
                # Generate embedding for search query
                model = self._get_embedding_model()
                if model is None:
                    return []
                    
                query_embedding = model.encode([search_text])[0].tolist()
                
                # Prepare metadata filters
                where_filters = {}
                if client_id:
                    where_filters["client_id"] = client_id
                if workflow_name:
                    where_filters["workflow_name"] = workflow_name
                if status_filter:
                    where_filters["status"] = {"$in": status_filter}
                
                # Perform vector search
                search_results = self._collection.query(
                    query_embeddings=[query_embedding],
                    n_results=min(max_results, self.max_results),
                    where=where_filters if where_filters else None,
                    include=["metadatas", "documents", "distances"]
                )
                
                # Convert results to SemanticSearchResult objects
                results = []
                if search_results["ids"] and len(search_results["ids"]) > 0:
                    for i, session_id in enumerate(search_results["ids"][0]):
                        # Calculate similarity score (ChromaDB returns distances)
                        distance = search_results["distances"][0][i]
                        similarity_score = max(0.0, 1.0 - distance)  # Convert distance to similarity
                        
                        # Skip results below minimum similarity
                        if similarity_score < min_similarity:
                            continue
                            
                        # Create metadata object (deserialize datetime strings and JSON)
                        metadata_dict = dict(search_results["metadatas"][0][i])
                        for key, value in metadata_dict.items():
                            if isinstance(value, str) and (key.endswith('_at') or key.endswith('_time') or key.endswith('_updated')):
                                with contextlib.suppress(ValueError, TypeError):
                                    dt = datetime.fromisoformat(value)
                                    # Ensure timezone awareness - if naive, assume UTC
                                    if dt.tzinfo is None:
                                        dt = dt.replace(tzinfo=UTC)
                                    metadata_dict[key] = dt
                            elif isinstance(value, str) and key == 'node_outputs':
                                # Deserialize node_outputs JSON string back to dict
                                try:
                                    metadata_dict[key] = json.loads(value) if value else {}
                                except (ValueError, TypeError, json.JSONDecodeError):
                                    # If JSON parsing fails, use empty dict as fallback
                                    metadata_dict[key] = {}
                        metadata = CacheMetadata(**metadata_dict)
                        
                        # Get matching text
                        matching_text = search_results["documents"][0][i]
                        
                        result = SemanticSearchResult(
                            session_id=session_id,
                            similarity_score=round(similarity_score, 4),
                            metadata=metadata,
                            matching_text=matching_text
                        )
                        results.append(result)
                
                # Sort by similarity score (highest first)
                results.sort(key=lambda x: x.similarity_score, reverse=True)
                return results
                
        except Exception as e:
            print(f"Warning: Semantic search failed: {e}")
            return []

    def find_similar_workflows(
        self, 
        workflow_state: DynamicWorkflowState, 
        max_results: int = 10,
        min_similarity: float = 0.3
    ) -> list[SemanticSearchResult]:
        """Find workflows similar to the given workflow state.
        
        Args:
            workflow_state: Workflow state to find similar ones for
            max_results: Maximum number of results to return
            min_similarity: Minimum similarity score
            
        Returns:
            List of similar workflow states
        """
        # Generate search text from the workflow state
        search_text = self._generate_embedding_text(workflow_state)
        
        # Perform search using direct parameters instead of query object
        results = self.semantic_search(
            search_text=search_text,
            client_id=workflow_state.client_id,  # Find similar workflows for same client
            max_results=max_results,
            min_similarity=min_similarity,
            include_inactive=True
        )
        
        # Filter out the current session
        return [r for r in results if r.session_id != workflow_state.session_id]

    def get_all_sessions_for_client(self, client_id: str) -> list[CacheMetadata]:
        """Get all cached sessions for a specific client.
        
        Args:
            client_id: Client ID to search for
            
        Returns:
            List of cache metadata for the client's sessions
        """
        return self._get_sessions_with_filter({"client_id": client_id})

    def get_all_sessions(self) -> list[CacheMetadata]:
        """Get all cached sessions across all clients.
        
        Returns:
            List of cache metadata for all sessions
        """
        return self._get_sessions_with_filter(None)

    def _get_sessions_with_filter(self, where_filter: dict | None) -> list[CacheMetadata]:
        """Helper method to get sessions with optional filtering.
        
        Args:
            where_filter: Optional WHERE filter for ChromaDB query
            
        Returns:
            List of cache metadata for matching sessions
        """
        if not self._ensure_initialized():
            return []
            
        try:
            with self._lock:
                # Query for sessions with optional filter
                results = self._collection.get(
                    where=where_filter,
                    include=["metadatas"]
                )
                
                if not results["metadatas"]:
                    return []
                    
                # Convert to metadata objects (deserialize datetime strings and JSON) and sort by last_updated
                metadatas = []
                for m in results["metadatas"]:
                    metadata_dict = dict(m)
                    for key, value in metadata_dict.items():
                        if isinstance(value, str) and (key.endswith('_at') or key.endswith('_time') or key.endswith('_updated')):
                            with contextlib.suppress(ValueError, TypeError):
                                dt = datetime.fromisoformat(value)
                                # Ensure timezone awareness - if naive, assume UTC
                                if dt.tzinfo is None:
                                    dt = dt.replace(tzinfo=UTC)
                                metadata_dict[key] = dt
                        elif isinstance(value, str) and key == 'node_outputs':
                            # Deserialize node_outputs JSON string back to dict
                            try:
                                metadata_dict[key] = json.loads(value) if value else {}
                            except (ValueError, TypeError, json.JSONDecodeError):
                                # If JSON parsing fails, use empty dict as fallback
                                metadata_dict[key] = {}
                    metadatas.append(CacheMetadata(**metadata_dict))
                
                # Sort by last_updated (now all timezone-aware)
                metadatas.sort(key=lambda x: x.last_updated, reverse=True)
                
                return metadatas
                
        except Exception as e:
            filter_desc = f"filter {where_filter}" if where_filter else "no filter"
            print(f"Warning: Failed to get sessions with {filter_desc}: {e}")
            return []

    def cleanup_old_entries(self, max_age_days: int = 30) -> int:
        """Remove cached entries older than specified days.
        
        Args:
            max_age_days: Maximum age in days for cached entries
            
        Returns:
            Number of entries removed
        """
        if not self._ensure_initialized():
            return 0
            
        try:
            with self._lock:
                # Calculate cutoff date
                from datetime import timedelta
                cutoff_date = datetime.now(UTC) - timedelta(days=max_age_days)
                
                # Get all entries with timestamps
                results = self._collection.get(include=["metadatas"])
                
                if not results["metadatas"]:
                    return 0
                    
                # Find entries to delete
                ids_to_delete = []
                for i, metadata_dict in enumerate(results["metadatas"]):
                    metadata = CacheMetadata(**metadata_dict)
                    if metadata.cache_created_at < cutoff_date:
                        ids_to_delete.append(results["ids"][i])
                
                # Delete old entries
                if ids_to_delete:
                    self._collection.delete(ids=ids_to_delete)
                    
                return len(ids_to_delete)
                
        except Exception as e:
            print(f"Warning: Failed to cleanup old entries: {e}")
            return 0

    def regenerate_embeddings_for_enhanced_search(self, force_regenerate: bool = False) -> int:
        """Regenerate embeddings for existing cache entries using enhanced text generation.
        
        This method should be called after updating the _generate_embedding_text method
        to ensure existing cached states benefit from improved semantic content.
        
        Args:
            force_regenerate: If True, regenerate all embeddings even if text appears unchanged.
                             Useful when embedding model changes or to ensure embeddings are current.
        
        Returns:
            Number of embeddings regenerated
        """
        if not self._ensure_initialized():
            return 0
            
        try:
            with self._lock:
                # Get all existing entries
                results = self._collection.get(include=["metadatas", "documents"])
                
                if not results["ids"]:
                    return 0
                
                model = self._get_embedding_model()
                if model is None:
                    print("Warning: Cannot regenerate embeddings - model not available")
                    return 0
                
                regenerated_count = 0
                
                for i, session_id in enumerate(results["ids"]):
                    try:
                        # Reconstruct state from metadata to generate enhanced embedding text
                        metadata_dict = dict(results["metadatas"][i])
                        
                        # Convert ISO datetime strings back to datetime objects
                        for key, value in metadata_dict.items():
                            if isinstance(value, str) and (key.endswith('_at') or key.endswith('_time') or key.endswith('_updated')):
                                with contextlib.suppress(ValueError, TypeError):
                                    dt = datetime.fromisoformat(value)
                                    # Ensure timezone awareness - if naive, assume UTC
                                    if dt.tzinfo is None:
                                        dt = dt.replace(tzinfo=UTC)
                                    metadata_dict[key] = dt
                        
                        metadata = CacheMetadata(**metadata_dict)
                        
                        # Create a minimal workflow state for embedding generation
                        state = DynamicWorkflowState(
                            session_id=metadata.session_id,
                            client_id=metadata.client_id,
                            workflow_name=metadata.workflow_name,
                            workflow_file=metadata.workflow_file,
                            current_node=metadata.current_node,
                            current_item=metadata.current_item,
                            status=metadata.status,
                            node_outputs=metadata.node_outputs,
                            created_at=metadata.created_at,
                            last_updated=metadata.last_updated,
                        )
                        
                        # Generate enhanced embedding text
                        enhanced_text = self._generate_embedding_text(state)
                        
                        # Update if text has changed OR if force_regenerate is True
                        original_text = results["documents"][i]
                        should_update = force_regenerate or enhanced_text != original_text
                        
                        if should_update:
                            # Generate new embedding (even for same text, embedding model may produce different vectors)
                            embedding = model.encode([enhanced_text])[0].tolist()
                            
                            # Prepare metadata with serializable datetime values
                            serializable_metadata = {}
                            for key, value in metadata_dict.items():
                                if isinstance(value, datetime):
                                    serializable_metadata[key] = value.isoformat()
                                else:
                                    serializable_metadata[key] = value
                            
                            # Update the entry with new embedding and text
                            self._collection.upsert(
                                ids=[session_id],
                                embeddings=[embedding],
                                documents=[enhanced_text],
                                metadatas=[serializable_metadata]
                            )
                            
                            regenerated_count += 1
                            
                    except Exception as e:
                        print(f"Warning: Failed to regenerate embedding for {session_id}: {e}")
                        continue
                
                return regenerated_count
                
        except Exception as e:
            print(f"Warning: Failed to regenerate embeddings: {e}")
            return 0

    def cleanup(self) -> None:
        """Cleanup cache resources."""
        with self._lock:
            if self._client:
                # ChromaDB client doesn't need explicit cleanup
                pass
            self._initialized = False
            self._client = None
            self._collection = None
            # Keep embedding model loaded for reuse 