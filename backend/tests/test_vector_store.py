"""
Tests for vector_store.py - Phase 2: Embeddings and Supabase/pgvector operations.
"""
import os
import pytest
import numpy as np
from unittest.mock import Mock, patch, call
from types import SimpleNamespace
from uuid import uuid4

# Set test environment variables before importing modules
os.environ.setdefault("SESSION_SECRET", "test-secret-key-for-testing-only")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-service-role-key")
os.environ.setdefault("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
os.environ.setdefault("TOP_K", "4")
os.environ.setdefault("MIN_SIMILARITY", "0.0")

# Import after setting env vars
import services.vector_store as vector_store
from services.vector_store import (
    get_embedding_model,
    get_supabase_client,
    generate_embeddings,
    store_chunks,
    search_similar_chunks,
    delete_document,
    EmbeddingError,
    VectorStoreConnectionError,
    VectorStoreOperationError,
)


def reset_vector_store_globals():
    """Reset global state for vector store."""
    vector_store._embedding_model = None
    vector_store._supabase_client = None


def test_list_documents_deduplicates_local_and_remote_chunks(monkeypatch):
    duplicate_chunk = {
        "id": "chunk-1",
        "document_id": "doc-1",
        "workspace_id": "workspace-1",
        "pdf_name": "course.pdf",
        "page_number": 1,
        "chunk_index": 0,
        "created_at": "2026-01-01T00:00:00Z",
    }
    remote_second_chunk = {
        **duplicate_chunk,
        "id": "chunk-2",
        "page_number": 2,
        "chunk_index": 1,
    }
    monkeypatch.setattr(vector_store, "_load_local_vectors", lambda: [duplicate_chunk])
    monkeypatch.setattr(vector_store.config, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(vector_store.config, "SUPABASE_KEY", "test-key")
    client = Mock()
    query = client.table.return_value.select.return_value.order.return_value.range.return_value
    query.execute.return_value = SimpleNamespace(data=[duplicate_chunk, remote_second_chunk])
    monkeypatch.setattr(vector_store, "get_supabase_client", lambda: client)

    documents = vector_store.list_documents()

    assert len(documents) == 1
    assert documents[0]["document_id"] == "doc-1"
    assert documents[0]["chunks_count"] == 2
    assert documents[0]["pages_count"] == 2


def test_delete_document_only_removes_matching_workspace(monkeypatch):
    rows = [
        {"document_id": "doc-1", "workspace_id": "workspace-1"},
        {"document_id": "doc-1", "workspace_id": "workspace-2"},
    ]
    saved = []
    monkeypatch.setattr(vector_store.config, "SUPABASE_URL", None)
    monkeypatch.setattr(vector_store.config, "SUPABASE_KEY", None)
    monkeypatch.setattr(vector_store, "_load_local_vectors", lambda: rows)
    monkeypatch.setattr(vector_store, "_save_local_vectors", lambda remaining: saved.extend(remaining))

    deleted = vector_store.delete_document("workspace-1", "doc-1")

    assert deleted == 1
    assert saved == [rows[1]]


class TestEmbeddingModel:
    """Tests for embedding model loading and generation."""

    def setup_method(self):
        """Reset global state before each test."""
        reset_vector_store_globals()

    def test_get_embedding_model_loads_once(self):
        """Test that embedding model is loaded only once (singleton)."""
        model1 = get_embedding_model()
        model2 = get_embedding_model()
        assert model1 is model2

    def test_embedding_dimension_is_384(self):
        """Test that embedding model produces 384-dimensional vectors."""
        model = get_embedding_model()
        embeddings = model.encode(["test sentence"])
        assert embeddings.shape[1] == 384

    def test_generate_embeddings_returns_list_of_lists(self):
        """Test that generate_embeddings returns list of float lists."""
        texts = ["First sentence.", "Second sentence."]
        embeddings = generate_embeddings(texts)
        
        assert isinstance(embeddings, list)
        assert len(embeddings) == 2
        assert all(isinstance(e, list) for e in embeddings)
        assert all(len(e) == 384 for e in embeddings)
        assert all(isinstance(v, float) for e in embeddings for v in e)

    def test_generate_embeddings_empty_list(self):
        """Test that empty input returns empty list."""
        embeddings = generate_embeddings([])
        assert embeddings == []

    def test_generate_embeddings_single_text(self):
        """Test embedding generation for single text."""
        embeddings = generate_embeddings(["Single test sentence."])
        assert len(embeddings) == 1
        assert len(embeddings[0]) == 384

    def test_generate_embeddings_uses_zero_gpu_in_hugging_face_space(self, monkeypatch):
        monkeypatch.setenv("SPACE_ID", "adraME/ai_bot_diploma")
        gpu_result = [[0.1] * 384]
        gpu_encoder = Mock(return_value=gpu_result)
        monkeypatch.setattr(
            vector_store,
            "generate_embeddings_on_zero_gpu",
            gpu_encoder,
        )

        assert generate_embeddings(["test"]) == gpu_result
        gpu_encoder.assert_called_once_with(["test"])

    def test_generate_embeddings_uses_cpu_outside_hugging_face_space(self, monkeypatch):
        monkeypatch.delenv("SPACE_ID", raising=False)
        model = Mock()
        model.encode.return_value = np.array([[0.1] * 384])
        monkeypatch.setattr(vector_store, "get_embedding_model", lambda: model)

        embeddings = generate_embeddings(["test"])

        assert embeddings == [[0.1] * 384]
        model.to.assert_not_called()
        model.encode.assert_called_once_with(["test"], convert_to_numpy=True)

    def test_zero_gpu_event_handler_generates_embeddings(self, monkeypatch):
        model = Mock()
        model.encode.return_value = np.array([[0.1] * 384])
        monkeypatch.setattr(vector_store, "get_embedding_model", lambda: model)

        embeddings = vector_store.generate_embeddings_on_zero_gpu(["test"])

        assert embeddings == [[0.1] * 384]
        model.encode.assert_called_once_with(["test"], convert_to_numpy=True)

    def test_zero_gpu_event_handler_rejects_invalid_input(self):
        with pytest.raises(ValueError, match="JSON array of text strings"):
            vector_store.generate_embeddings_on_zero_gpu({"text": "test"})

    def test_embedding_model_uses_cuda_in_hugging_face_space(self, monkeypatch):
        monkeypatch.setenv("SPACE_ID", "adraME/ai_bot_diploma")
        model = Mock()
        model.encode.return_value = np.array([[0.1] * 384])
        constructor = Mock(return_value=model)
        monkeypatch.setattr(vector_store, "SentenceTransformer", constructor)

        assert get_embedding_model() is model
        constructor.assert_called_once_with(
            vector_store.config.EMBEDDING_MODEL,
            device="cuda",
        )


class TestSupabaseClient:
    """Tests for Supabase client initialization."""

    def setup_method(self):
        """Reset global state before each test."""
        reset_vector_store_globals()

    @patch("services.vector_store.create_client")
    def test_get_supabase_client_initializes_once(self, mock_create_client):
        """Test that Supabase client is initialized only once."""
        mock_client = Mock()
        mock_create_client.return_value = mock_client
        
        client1 = get_supabase_client()
        client2 = get_supabase_client()
        
        assert client1 is client2
        assert client1 is mock_client
        mock_create_client.assert_called_once()

    @patch("services.vector_store.create_client")
    def test_get_supabase_client_uses_config(self, mock_create_client):
        """Test that client uses config values."""
        mock_client = Mock()
        mock_create_client.return_value = mock_client
        
        get_supabase_client()
        
        mock_create_client.assert_called_once_with(
            "https://test.supabase.co",
            "test-service-role-key"
        )

    def test_get_supabase_client_raises_without_config(self):
        """Test that client raises error without config."""
        reset_vector_store_globals()
        
        with patch("services.vector_store.config") as mock_config:
            mock_config.SUPABASE_URL = None
            mock_config.SUPABASE_KEY = "key"
            
            with pytest.raises(VectorStoreConnectionError) as exc_info:
                get_supabase_client()
            assert "SUPABASE_URL and SUPABASE_KEY must be configured" in str(exc_info.value)

    def test_get_supabase_client_raises_on_init_failure(self):
        """Test that client raises on initialization failure."""
        reset_vector_store_globals()
        
        with patch("services.vector_store.create_client") as mock_create_client:
            mock_create_client.side_effect = Exception("Connection failed")
            
            with pytest.raises(VectorStoreConnectionError) as exc_info:
                get_supabase_client()
            assert "Failed to initialize Supabase client" in str(exc_info.value)


class TestStoreChunks:
    """Tests for storing chunks in vector database."""

    def setup_method(self):
        """Reset global state before each test."""
        reset_vector_store_globals()

    @patch("services.vector_store.get_supabase_client")
    @patch("services.vector_store.generate_embeddings")
    def test_store_chunks_success(self, mock_generate_embeddings, mock_get_client):
        """Test successful chunk storage."""
        # Setup mocks
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        mock_generate_embeddings.return_value = [[0.1] * 384, [0.2] * 384]
        
        mock_result = Mock()
        mock_result.data = [{"id": "1"}, {"id": "2"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_result
        
        # Test data
        chunks = [
            {"content": "First chunk content.", "metadata": {"page_number": 1, "chunk_index": 0, "pdf_name": "test.pdf"}},
            {"content": "Second chunk content.", "metadata": {"page_number": 1, "chunk_index": 1, "pdf_name": "test.pdf"}},
        ]
        workspace_id = str(uuid4())
        document_id = str(uuid4())
        
        # Call function
        count = store_chunks(chunks, workspace_id, document_id)
        
        # Assertions
        assert count == 2
        mock_generate_embeddings.assert_called_once_with(["First chunk content.", "Second chunk content."])
        mock_client.table.assert_called_once_with("documents")

    @patch("services.vector_store.get_supabase_client")
    @patch("services.vector_store.generate_embeddings")
    def test_store_chunks_empty_list(self, mock_generate_embeddings, mock_get_client):
        """Test storing empty chunk list returns 0."""
        count = store_chunks([], str(uuid4()), str(uuid4()))
        assert count == 0
        mock_generate_embeddings.assert_not_called()
        mock_get_client.assert_not_called()

    @patch("services.vector_store.get_supabase_client")
    @patch("services.vector_store.generate_embeddings")
    def test_store_chunks_batches_large_list(self, mock_generate_embeddings, mock_get_client):
        """Test that large chunk lists are batched."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        # Create 250 chunks (more than batch size of 100)
        chunks = [
            {"content": f"Chunk {i}.", "metadata": {"page_number": 1, "chunk_index": i, "pdf_name": "test.pdf"}}
            for i in range(250)
        ]
        mock_generate_embeddings.return_value = [[0.1] * 384] * 250
        
        # Mock returns different batch sizes: 100, 100, 50
        mock_results = [
            Mock(data=[{"id": str(i)} for i in range(100)]),
            Mock(data=[{"id": str(i)} for i in range(100, 200)]),
            Mock(data=[{"id": str(i)} for i in range(200, 250)]),
        ]
        mock_client.table.return_value.insert.return_value.execute.side_effect = mock_results
        
        count = store_chunks(chunks, str(uuid4()), str(uuid4()))
        
        assert count == 250
        # Should have been called 3 times (100 + 100 + 50)
        assert mock_client.table.return_value.insert.call_count == 3

    @patch("services.vector_store.get_supabase_client")
    @patch("services.vector_store.generate_embeddings")
    def test_store_chunks_embedding_error(self, mock_generate_embeddings, mock_get_client):
        """Test that embedding errors are wrapped in VectorStoreOperationError."""
        mock_generate_embeddings.side_effect = EmbeddingError("Model failed")
        
        chunks = [{"content": "Test", "metadata": {"page_number": 1, "chunk_index": 0, "pdf_name": "test.pdf"}}]
        
        with pytest.raises(VectorStoreOperationError) as exc_info:
            store_chunks(chunks, str(uuid4()), str(uuid4()))
        assert "Failed to store chunks" in str(exc_info.value)

    @patch("services.vector_store.get_supabase_client")
    @patch("services.vector_store.generate_embeddings")
    def test_store_chunks_db_error(self, mock_generate_embeddings, mock_get_client):
        """Test that database errors are wrapped."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_generate_embeddings.return_value = [[0.1] * 384]
        
        mock_client.table.return_value.insert.return_value.execute.side_effect = Exception("DB error")
        
        chunks = [{"content": "Test", "metadata": {"page_number": 1, "chunk_index": 0, "pdf_name": "test.pdf"}}]
        
        with pytest.raises(VectorStoreOperationError) as exc_info:
            store_chunks(chunks, str(uuid4()), str(uuid4()))
        assert "Failed to store chunks" in str(exc_info.value)


class TestSearchSimilarChunks:
    """Tests for searching similar chunks."""

    def setup_method(self):
        """Reset global state before each test."""
        reset_vector_store_globals()

    @patch("services.vector_store.get_supabase_client")
    @patch("services.vector_store.generate_embeddings")
    def test_search_similar_chunks_success(self, mock_generate_embeddings, mock_get_client):
        """Test successful similarity search."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        mock_generate_embeddings.return_value = [[0.1] * 384]
        
        mock_result = Mock()
        mock_result.data = [
            {
                "id": "1",
                "document_id": "doc-1",
                "pdf_name": "test.pdf",
                "content": "Matching content.",
                "metadata": {"key": "value"},
                "page_number": 1,
                "chunk_index": 0,
                "similarity": 0.85,
            }
        ]
        mock_client.rpc.return_value.execute.return_value = mock_result
        
        workspace_id = str(uuid4())
        document_id = str(uuid4())
        
        results = search_similar_chunks(
            query="test query",
            workspace_id=workspace_id,
            document_id=document_id,
            top_k=4,
        )
        
        assert len(results) == 1
        assert results[0]["similarity"] == 0.85
        assert results[0]["content"] == "Matching content."
        mock_client.rpc.assert_called_once()
        call_args = mock_client.rpc.call_args
        assert call_args[0][0] == "match_documents"
        # rpc is called with (function_name, params_dict) - params are in call_args[0][1]
        params = call_args[0][1]
        assert params["query_embedding"] == [0.1] * 384
        assert params["match_count"] == 4
        assert params["filter_workspace_id"] == workspace_id
        assert params["filter_document_id"] == document_id

    @patch("services.vector_store.get_supabase_client")
    @patch("services.vector_store.generate_embeddings")
    def test_search_similar_chunks_empty_results(self, mock_generate_embeddings, mock_get_client):
        """Test search with no results."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        mock_generate_embeddings.return_value = [[0.1] * 384]
        
        mock_result = Mock()
        mock_result.data = []
        mock_client.rpc.return_value.execute.return_value = mock_result
        
        results = search_similar_chunks(
            query="test query",
            workspace_id=str(uuid4()),
            document_id=str(uuid4()),
        )
        
        assert results == []

    @patch("services.vector_store.get_supabase_client")
    @patch("services.vector_store.generate_embeddings")
    def test_search_similar_chunks_uses_default_top_k(self, mock_generate_embeddings, mock_get_client):
        """Test that default top_k from config is used."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_generate_embeddings.return_value = [[0.1] * 384]
        mock_client.rpc.return_value.execute.return_value = Mock(data=[])
        
        search_similar_chunks(
            query="test",
            workspace_id=str(uuid4()),
            document_id=str(uuid4()),
        )
        
        # Check that match_count=4 (default TOP_K) was used
        call_args = mock_client.rpc.call_args
        params = call_args[0][1]
        assert params["match_count"] == 4

    @patch("services.vector_store.get_supabase_client")
    @patch("services.vector_store.generate_embeddings")
    def test_search_similar_chunks_embedding_error(self, mock_generate_embeddings, mock_get_client):
        """Test that embedding errors are wrapped in VectorStoreOperationError."""
        mock_generate_embeddings.side_effect = EmbeddingError("Model failed")
        
        with pytest.raises(VectorStoreOperationError) as exc_info:
            search_similar_chunks("test", str(uuid4()), str(uuid4()))
        assert "Failed to search similar chunks" in str(exc_info.value)

    @patch("services.vector_store.get_supabase_client")
    @patch("services.vector_store.generate_embeddings")
    def test_search_similar_chunks_db_error(self, mock_generate_embeddings, mock_get_client):
        """Test that database errors are wrapped."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_generate_embeddings.return_value = [[0.1] * 384]
        
        mock_client.rpc.return_value.execute.side_effect = Exception("DB error")
        
        with pytest.raises(VectorStoreOperationError) as exc_info:
            search_similar_chunks("test", str(uuid4()), str(uuid4()))
        assert "Failed to search similar chunks" in str(exc_info.value)


class TestDeleteDocument:
    """Tests for document deletion."""

    def setup_method(self):
        """Reset global state before each test."""
        reset_vector_store_globals()

    @patch("services.vector_store.get_supabase_client")
    def test_delete_document_success(self, mock_get_client):
        """Test successful document deletion."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        mock_result = Mock()
        mock_result.data = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result
        
        workspace_id = str(uuid4())
        document_id = str(uuid4())
        
        count = delete_document(workspace_id, document_id)
        
        assert count == 3
        mock_client.table.assert_called_once_with("documents")

    @patch("services.vector_store.get_supabase_client")
    def test_delete_document_not_found(self, mock_get_client):
        """Test deletion when document doesn't exist."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        mock_result = Mock()
        mock_result.data = []
        mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = mock_result
        
        count = delete_document(str(uuid4()), str(uuid4()))
        
        assert count == 0

    @patch("services.vector_store.get_supabase_client")
    def test_delete_document_db_error(self, mock_get_client):
        """Test that database errors are wrapped."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.side_effect = Exception("DB error")
        
        with pytest.raises(VectorStoreOperationError) as exc_info:
            delete_document(str(uuid4()), str(uuid4()))
        assert "Failed to delete document" in str(exc_info.value)


class TestWorkspaceIsolation:
    """Tests for workspace/data isolation."""

    def setup_method(self):
        """Reset global state before each test."""
        reset_vector_store_globals()

    @patch("services.vector_store.get_supabase_client")
    @patch("services.vector_store.generate_embeddings")
    def test_search_filters_by_workspace_and_document(self, mock_generate_embeddings, mock_get_client):
        """Test that search RPC filters by both workspace_id and document_id."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        mock_generate_embeddings.return_value = [[0.1] * 384]
        mock_client.rpc.return_value.execute.return_value = Mock(data=[])
        
        workspace_id = "ws-123"
        document_id = "doc-456"
        
        search_similar_chunks("test", workspace_id, document_id)
        
        call_args = mock_client.rpc.call_args
        params = call_args[0][1]
        assert params["filter_workspace_id"] == workspace_id
        assert params["filter_document_id"] == document_id

    @patch("services.vector_store.get_supabase_client")
    def test_delete_filters_by_workspace_and_document(self, mock_get_client):
        """Test that delete filters by both workspace_id and document_id."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        
        mock_result = Mock()
        mock_result.data = []
        
        # Create a chain where each eq() returns the same mock
        mock_eq = Mock()
        mock_eq.eq.return_value = mock_eq
        mock_eq.execute.return_value = mock_result
        mock_client.table.return_value.delete.return_value = mock_eq
        
        workspace_id = "ws-123"
        document_id = "doc-456"
        
        delete_document(workspace_id, document_id)
        
        # Verify the chain of eq() calls
        eq_calls = mock_eq.eq.call_args_list
        assert len(eq_calls) >= 2
        # First eq should be workspace_id, second should be document_id
        assert eq_calls[0] == call("workspace_id", workspace_id)
        assert eq_calls[1] == call("document_id", document_id)


class TestEmbeddingQuality:
    """Tests for embedding quality and consistency."""

    def setup_method(self):
        """Reset global state before each test."""
        reset_vector_store_globals()

    def test_embeddings_are_deterministic(self):
        """Test that same text produces same embedding."""
        model = get_embedding_model()
        emb1 = model.encode(["test sentence"])
        emb2 = model.encode(["test sentence"])
        assert (emb1 == emb2).all()

    def test_different_texts_produce_different_embeddings(self):
        """Test that different texts produce different embeddings."""
        model = get_embedding_model()
        emb1 = model.encode(["first sentence"])
        emb2 = model.encode(["second sentence"])
        assert not (emb1 == emb2).all()

    def test_embedding_values_are_reasonable(self):
        """Test that embedding values are in reasonable range."""
        model = get_embedding_model()
        emb = model.encode(["test sentence"])
        # Embeddings should be normalized (unit vectors for cosine similarity)
        # Values should be roughly in [-1, 1] range
        assert emb.min() >= -1.0
        assert emb.max() <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])