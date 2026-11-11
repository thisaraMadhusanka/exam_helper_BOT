"""
Vector store service for PDF RAG Assistant.
Handles embeddings generation, Supabase/pgvector operations,
and local vector persistence fallback for reliable offline/local search.
"""
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import numpy as np
import spaces
from sentence_transformers import SentenceTransformer
from supabase import create_client, Client

from utils.config import config

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOCAL_VECTORS_FILE = DATA_DIR / "local_vector_store.json"


class VectorStoreError(Exception):
    """Base exception for vector store errors."""
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class EmbeddingError(VectorStoreError):
    """Error generating embeddings."""
    def __init__(self, message: str = "Failed to generate embeddings"):
        super().__init__("EMBEDDING_ERROR", message)


class VectorStoreConnectionError(VectorStoreError):
    """Error connecting to vector database."""
    def __init__(self, message: str = "Failed to connect to vector database"):
        super().__init__("VECTOR_STORE_CONNECTION_ERROR", message)


class VectorStoreOperationError(VectorStoreError):
    """Error during vector store operation."""
    def __init__(self, message: str = "Vector store operation failed"):
        super().__init__("VECTOR_STORE_OPERATION_ERROR", message)


# Global embedding model instance (loaded once on demand locally, at startup in Spaces)
_embedding_model: SentenceTransformer | None = None
_supabase_client: Client | None = None
_embedding_lock = threading.RLock()


def _ensure_data_dir() -> None:
    """Ensure data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_local_vectors() -> list[dict[str, Any]]:
    """Load cached vectors from local storage."""
    _ensure_data_dir()
    if not LOCAL_VECTORS_FILE.exists():
        return []
    try:
        with open(LOCAL_VECTORS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load local vectors: %s", e)
        return []


def _save_local_vectors(vectors: list[dict[str, Any]]) -> None:
    """Save vectors to local storage."""
    _ensure_data_dir()
    try:
        with open(LOCAL_VECTORS_FILE, "w", encoding="utf-8") as f:
            json.dump(vectors, f, indent=1, default=str)
    except Exception as e:
        logger.warning("Failed to save local vectors: %s", e)


def get_embedding_model() -> SentenceTransformer:
    """
    Get or initialize the embedding model singleton on the appropriate device.
    """
    global _embedding_model

    with _embedding_lock:
        if _embedding_model is None:
            try:
                logger.info("Loading embedding model: %s", config.EMBEDDING_MODEL)
                device = "cuda" if os.getenv("SPACE_ID") else "cpu"
                _embedding_model = SentenceTransformer(config.EMBEDDING_MODEL, device=device)
                test_embedding = _embedding_model.encode(["test"])
                dim = test_embedding.shape[1]
                expected_dim = 384
                if dim != expected_dim:
                    raise EmbeddingError(
                        f"Embedding dimension mismatch: expected {expected_dim}, got {dim}"
                    )
                logger.info("Embedding model loaded successfully (dimension: %d)", dim)
            except Exception as e:
                logger.error("Failed to load embedding model: %s", e)
                raise EmbeddingError(f"Failed to load embedding model: {e}")

        return _embedding_model


def get_supabase_client() -> Client:
    """
    Get or initialize the Supabase client singleton.
    """
    global _supabase_client

    if _supabase_client is None:
        if not config.SUPABASE_URL or not config.SUPABASE_KEY:
            raise VectorStoreConnectionError(
                "SUPABASE_URL and SUPABASE_KEY must be configured"
            )
        try:
            _supabase_client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
            logger.info("Supabase client initialized")
        except Exception as e:
            logger.error("Failed to initialize Supabase client: %s", e)
            raise VectorStoreConnectionError(f"Failed to initialize Supabase client: {e}")

    return _supabase_client


@spaces.GPU(duration=120)
def generate_embeddings_on_zero_gpu(texts: list[str]) -> list[list[float]]:
    """ZeroGPU event handler for embedding generation."""
    if not isinstance(texts, list) or not all(isinstance(text, str) for text in texts):
        raise ValueError("Expected a JSON array of text strings")
    if not texts:
        return []

    with _embedding_lock:
        model = get_embedding_model()
        embeddings = model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings on ZeroGPU in Spaces and on CPU in local development.
    """
    if not texts:
        return []

    try:
        if os.getenv("SPACE_ID"):
            return generate_embeddings_on_zero_gpu(texts)

        with _embedding_lock:
            model = get_embedding_model()
            embeddings = model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()
    except Exception as e:
        logger.error("Failed to generate embeddings: %s", e)
        raise EmbeddingError(f"Failed to generate embeddings: {e}")


if os.getenv("SPACE_ID"):
    get_embedding_model()


def store_chunks(
    chunks: list[dict[str, Any]],
    workspace_id: str,
    document_id: str
) -> int:
    """
    Store document chunks with embeddings in local store and Supabase.
    """
    if not chunks:
        return 0

    try:
        # Prepare texts for embedding
        texts = [chunk["content"] for chunk in chunks]
        embeddings = generate_embeddings(texts)

        # Prepare rows
        rows = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            metadata = chunk.get("metadata", {})
            chunk_id = str(chunk.get("id") or f"{document_id}_{i}")
            rows.append({
                "id": chunk_id,
                "workspace_id": str(workspace_id),
                "document_id": str(document_id),
                "content": chunk["content"],
                "embedding": embedding,
                "metadata": metadata,
                "pdf_name": metadata.get("pdf_name", "document.pdf"),
                "page_number": metadata.get("page_number", 1),
                "chunk_index": metadata.get("chunk_index", i),
            })

        # Save to local vector store first (guarantees local availability)
        local_store = _load_local_vectors()
        # Remove any existing rows with the same document_id
        local_store = [r for r in local_store if r.get("document_id") != str(document_id)]
        local_store.extend(rows)
        _save_local_vectors(local_store)
        total_inserted = len(rows)

        # Also push to Supabase if reachable
        if config.SUPABASE_URL and config.SUPABASE_KEY:
            try:
                client = get_supabase_client()
                batch_size = 100
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    client.table("documents").insert(batch).execute()
                logger.info("Pushed %d chunks to Supabase for document %s", len(rows), document_id)
            except Exception as e:
                logger.info("Supabase insert skipped or offline: %s", e)

        logger.info("Stored %d chunks for document %s", total_inserted, document_id)
        return total_inserted

    except Exception as e:
        logger.error("Failed to store chunks: %s", e)
        raise VectorStoreOperationError(f"Failed to store chunks: {e}")


def search_similar_chunks(
    query: str | list[str],
    workspace_id: Optional[str] = None,
    document_id: Optional[str] = None,
    document_ids: Optional[list[str]] = None,
    top_k: int | None = None,
    min_similarity: Optional[float] = None,
    metadata_filters: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """
    Search for similar chunks using vector similarity.
    Supports single query or multi-query list (for query expansion),
    single document_id or list of document_ids, metadata filtering,
    and similarity thresholding.
    Attempts Supabase RPC first, with fallback to local cosine similarity search.
    Strictly preserves workspace isolation.
    """
    if top_k is None:
        top_k = config.TOP_K

    queries = [query] if isinstance(query, str) else [q for q in query if q.strip()]
    if not queries:
        return []

    # Consolidate target document IDs
    target_doc_ids: set[str] = set()
    if document_id:
        target_doc_ids.add(str(document_id))
    if document_ids:
        for did in document_ids:
            if did:
                target_doc_ids.add(str(did))

    # 1. Generate query embeddings for all queries
    query_embeddings = generate_embeddings(queries)
    normalized_query_vecs = []
    for q_emb in query_embeddings:
        q_vec = np.array(q_emb, dtype=np.float32)
        norm_q = np.linalg.norm(q_vec)
        if norm_q > 0:
            q_vec = q_vec / norm_q
        normalized_query_vecs.append(q_vec)

    # 2. Try Supabase if a single query and single document_id and workspace_id are provided
    if (
        config.SUPABASE_URL
        and config.SUPABASE_KEY
        and len(target_doc_ids) == 1
        and workspace_id
        and len(queries) == 1
    ):
        try:
            client = get_supabase_client()
            single_doc_id = next(iter(target_doc_ids))
            result = client.rpc("match_documents", {
                "query_embedding": query_embeddings[0],
                "match_count": top_k * 2 if min_similarity else top_k,
                "filter_workspace_id": str(workspace_id),
                "filter_document_id": str(single_doc_id),
            }).execute()

            if result.data:
                logger.info("Found %d similar chunks via Supabase RPC", len(result.data))
                res_chunks = result.data
                if min_similarity is not None:
                    res_chunks = [c for c in res_chunks if c.get("similarity", 0.0) >= min_similarity]
                return res_chunks[:top_k]
        except Exception as e:
            logger.info("Supabase RPC search skipped: %s", e)

    # 3. Local Vector Search Fallback (multi-query and flexible document-set support)
    local_store = _load_local_vectors()
    if not local_store:
        logger.info("No local chunks stored")
        return []

    # Strictly enforce workspace isolation if workspace_id is provided
    candidates = local_store
    if workspace_id:
        candidates = [c for c in candidates if str(c.get("workspace_id")) == str(workspace_id)]
        if not candidates:
            logger.info("No candidate chunks for workspace_id=%s", workspace_id)
            return []

    # Enforce document filtering if requested
    if target_doc_ids:
        candidates = [c for c in candidates if str(c.get("document_id")) in target_doc_ids]
        if not candidates:
            logger.info("No candidate chunks match document_ids=%s in workspace", target_doc_ids)
            return []

    # Apply metadata filters if provided
    if metadata_filters:
        for key, val in metadata_filters.items():
            candidates = [c for c in candidates if c.get("metadata", {}).get(key) == val]

    if not candidates:
        return []

    scored_chunks: list[dict[str, Any]] = []
    for c in candidates:
        emb = c.get("embedding")
        if not emb:
            continue
        c_vec = np.array(emb, dtype=np.float32)
        norm_c = np.linalg.norm(c_vec)
        if norm_c > 0:
            c_vec = c_vec / norm_c

        # In multi-query retrieval, compute cosine similarity against each query vector and take maximum
        sims = [float(np.dot(q_vec, c_vec)) for q_vec in normalized_query_vecs]
        best_sim = max(sims) if sims else 0.0

        if min_similarity is not None and best_sim < min_similarity:
            continue

        scored_chunks.append({
            "id": c.get("id"),
            "document_id": c.get("document_id"),
            "pdf_name": c.get("pdf_name", "document.pdf"),
            "content": c.get("content", ""),
            "metadata": c.get("metadata", {}),
            "page_number": c.get("page_number", 1),
            "chunk_index": c.get("chunk_index", 0),
            "similarity": round(best_sim, 4),
        })

    # Sort by cosine similarity descending
    scored_chunks.sort(key=lambda x: x["similarity"], reverse=True)
    results = scored_chunks[:top_k]
    logger.info(
        "Vector search completed: queries=%d, candidates=%d, results=%d (best similarity: %.4f)",
        len(queries), len(candidates), len(results), results[0]["similarity"] if results else 0.0
    )
    return results


def get_chunk_neighbors(
    chunks: list[dict[str, Any]],
    window: int = 1,
    workspace_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Retrieve neighboring chunks (window preceding and succeeding) for the given chunks.
    Preserves context continuity and returns all chunks including neighbors,
    annotated with is_neighbor=True/False, deduplicated and ordered by page and chunk_index.
    """
    if not chunks:
        return []

    local_store = _load_local_vectors()
    if not local_store:
        return chunks

    # Build map of (document_id, chunk_index) -> chunk
    store_map: dict[tuple[str, int], dict[str, Any]] = {}
    for c in local_store:
        if workspace_id and str(c.get("workspace_id")) != str(workspace_id):
            continue
        doc_id = str(c.get("document_id"))
        idx = int(c.get("chunk_index", 0))
        store_map[(doc_id, idx)] = c

    # Collect chunk IDs and indices to retrieve
    selected: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        cid = str(chunk.get("id") or uuid4())
        selected[cid] = {**chunk, "is_neighbor": False}

        doc_id = str(chunk.get("document_id") or "")
        if not doc_id:
            continue
        curr_idx = int(chunk.get("chunk_index", 0))

        for offset in range(-window, window + 1):
            if offset == 0:
                continue
            neighbor_key = (doc_id, curr_idx + offset)
            if neighbor_key in store_map:
                nc = store_map[neighbor_key]
                nid = str(nc.get("id"))
                if nid not in selected:
                    selected[nid] = {
                        "id": nid,
                        "document_id": nc.get("document_id"),
                        "pdf_name": nc.get("pdf_name", "document.pdf"),
                        "content": nc.get("content", ""),
                        "metadata": nc.get("metadata", {}),
                        "page_number": nc.get("page_number", 1),
                        "chunk_index": nc.get("chunk_index", 0),
                        "similarity": round(float(chunk.get("similarity", 0.0) * 0.9), 4),
                        "is_neighbor": True,
                    }

    # Sort results primarily by document_id, then page_number, then chunk_index
    ordered = list(selected.values())
    ordered.sort(key=lambda x: (str(x.get("document_id", "")), int(x.get("page_number", 1)), int(x.get("chunk_index", 0))))
    return ordered


def delete_document(workspace_id: Optional[str], document_id: str) -> int:
    """
    Delete all chunks for a document within the requested workspace (or across workspaces if workspace_id is None).
    """
    deleted_count = 0
    if config.SUPABASE_URL and config.SUPABASE_KEY:
        try:
            client = get_supabase_client()
            query = client.table("documents").delete().eq("document_id", str(document_id))
            if workspace_id:
                query = query.eq("workspace_id", str(workspace_id))
            result = query.execute()
            deleted_count = len(result.data or [])
        except Exception as e:
            logger.error("Failed to delete document %s in workspace %s: %s", document_id, workspace_id, e)
            raise VectorStoreOperationError(f"Failed to delete document: {e}") from e

    local_store = _load_local_vectors()
    remaining = [
        chunk for chunk in local_store
        if not (
            (workspace_id is None or str(chunk.get("workspace_id")) == str(workspace_id))
            and str(chunk.get("document_id")) == str(document_id)
        )
    ]
    local_deleted_count = len(local_store) - len(remaining)
    _save_local_vectors(remaining)

    if not config.SUPABASE_URL or not config.SUPABASE_KEY:
        deleted_count = local_deleted_count

    return deleted_count


def get_document_chunk_count(workspace_id: str, document_id: str) -> int:
    """
    Get the number of chunks for a document.
    """
    local_store = _load_local_vectors()
    count = sum(1 for c in local_store if str(c.get("document_id")) == str(document_id))
    return count


def list_documents() -> list[dict[str, Any]]:
    """List unique indexed PDFs using local vectors and the configured database."""
    rows = _load_local_vectors()

    if config.SUPABASE_URL and config.SUPABASE_KEY:
        try:
            client = get_supabase_client()
            offset = 0
            page_size = 1000
            while True:
                result = (
                    client.table("documents")
                    .select("id,document_id,workspace_id,pdf_name,page_number,chunk_index,created_at")
                    .order("created_at", desc=True)
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                page = result.data or []
                rows.extend(page)
                if len(page) < page_size:
                    break
                offset += page_size
        except Exception as e:
            logger.warning("Unable to read complete document inventory from Supabase: %s", e)

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    page_numbers: dict[tuple[str, str], set[int]] = {}
    for row in rows:
        document_id = row.get("document_id")
        workspace_id = row.get("workspace_id")
        if not document_id or not workspace_id:
            continue
        key = (str(workspace_id), str(document_id))
        document = grouped.setdefault(key, {
            "document_id": key[1],
            "workspace_id": key[0],
            "pdf_name": row.get("pdf_name") or "document.pdf",
            "pages_count": 0,
            "chunks_count": 0,
            "created_at": row.get("created_at") or "",
            "_chunk_keys": set(),
        })
        chunk_key = row.get("chunk_index")
        if chunk_key is None:
            chunk_key = row.get("id")
        if chunk_key is None:
            document["chunks_count"] += 1
        else:
            document["_chunk_keys"].add(str(chunk_key))
        try:
            page_numbers.setdefault(key, set()).add(int(row.get("page_number", 0)))
        except (TypeError, ValueError):
            pass
        document["pdf_name"] = row.get("pdf_name") or document["pdf_name"]
        created_at = row.get("created_at") or ""
        if created_at > document["created_at"]:
            document["created_at"] = created_at

    for key, document in grouped.items():
        document["pages_count"] = len(page_numbers.get(key, set()))
        document["chunks_count"] += len(document.pop("_chunk_keys"))

    return sorted(grouped.values(), key=lambda item: item["created_at"], reverse=True)
