"""
Knowledge Retriever Service for Phase 3.
Executes Step 3: Retrieves relevant knowledge chunks from Supabase / local vector store
using the multi-query search plan, document filtering, and neighboring chunk context windowing.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Any
from uuid import UUID

from services.vector_store import (
    search_similar_chunks,
    get_chunk_neighbors,
    VectorStoreError,
)
from services.question_analyzer import QuestionAnalysisResult

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeRetrievalResult:
    """Consolidated retrieval result from persistent knowledge base."""
    chunks: list[dict[str, Any]]
    documents_searched: list[str]
    topics_found: list[str]
    useful_chunks_count: int
    max_similarity: float
    raw_query_count: int = 0


def retrieve_knowledge(
    analysis: QuestionAnalysisResult,
    workspace_id: Optional[str] = None,
    document_id: Optional[str] = None,
    document_ids: Optional[list[str]] = None,
    top_k: int = 4,
    min_similarity: float = 0.20,
    include_neighbors: bool = True,
    search_fn: Optional[Any] = None,
) -> KnowledgeRetrievalResult:
    """
    Step 3: Access persistent knowledge base.
    Uses planned search queries, pgvector embeddings, and neighbor windowing.
    Preserves document names, actual page numbers, and chunk indices.
    """
    doc_id_list: list[str] = []
    if document_ids:
        doc_id_list.extend([str(d) for d in document_ids if d])
    if document_id and str(document_id) not in doc_id_list:
        doc_id_list.append(str(document_id))

    ws_id_str = str(workspace_id) if workspace_id else None

    # Search with planned queries
    queries = analysis.search_queries if analysis.search_queries else [analysis.intent]
    search_func = search_fn if search_fn is not None else search_similar_chunks

    try:
        raw_results = search_func(
            query=queries,
            workspace_id=ws_id_str,
            document_ids=doc_id_list if doc_id_list else None,
            top_k=top_k,
            min_similarity=None,
        )
    except VectorStoreError as e:
        logger.error("Vector store search failed: %s", e)
        raise

    if not raw_results:
        return KnowledgeRetrievalResult(
            chunks=[],
            documents_searched=[],
            topics_found=[],
            useful_chunks_count=0,
            max_similarity=0.0,
            raw_query_count=len(queries),
        )

    max_sim = max(r.get("similarity", 0.0) for r in raw_results)

    # Windowing: Retrieve neighboring chunks for context continuity
    if include_neighbors and raw_results:
        augmented_results = get_chunk_neighbors(
            chunks=raw_results,
            window=1,
            workspace_id=ws_id_str,
        )
    else:
        augmented_results = raw_results

    # Unique document filenames searched
    docs_found = sorted(list(set(c.get("pdf_name", "document.pdf") for c in augmented_results)))

    # Topics found from analysis
    topics_found = [analysis.topic]
    if analysis.subtopic and analysis.subtopic not in topics_found:
        topics_found.append(analysis.subtopic)

    logger.info(
        "Knowledge retrieval complete: queries=%d, raw_hits=%d, augmented=%d, docs=%s, max_sim=%.4f",
        len(queries), len(raw_results), len(augmented_results), docs_found, max_sim
    )

    return KnowledgeRetrievalResult(
        chunks=augmented_results,
        documents_searched=docs_found,
        topics_found=topics_found,
        useful_chunks_count=len(raw_results),
        max_similarity=max_sim,
        raw_query_count=len(queries),
    )
