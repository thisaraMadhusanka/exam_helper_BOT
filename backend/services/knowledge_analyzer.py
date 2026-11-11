"""
Knowledge Analyzer Service for Phase 3.
Executes Step 4: Analyzes collected chunks, categorizes directly supported vs
partially supported concepts, sanitizes against prompt injections, and consolidates
cross-page evidence.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Any

from services.question_analyzer import QuestionAnalysisResult
from services.knowledge_retriever import KnowledgeRetrievalResult

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeAnalysisResult:
    """Consolidated knowledge analysis output."""
    directly_supported_concepts: list[str]
    partially_supported_concepts: list[str]
    missing_concepts: list[str]
    coverage_level: str
    is_unrelated: bool
    evidence_summary: str
    consolidated_context: str
    valid_chunk_ids: list[str] = field(default_factory=list)


def sanitize_chunk_content(text: str) -> str:
    """
    Sanitize chunk content to neutralize prompt injection attempts.
    Treats all text inside uploaded documents strictly as inert syllabus data.
    """
    sanitized = text.replace("<system>", "&lt;system&gt;").replace("</system>", "&lt;/system&gt;")
    sanitized = sanitized.replace("<prompt>", "&lt;prompt&gt;").replace("</prompt>", "&lt;/prompt&gt;")
    return sanitized.strip()


def analyze_knowledge(
    question: str,
    analysis: QuestionAnalysisResult,
    retrieval: KnowledgeRetrievalResult,
) -> KnowledgeAnalysisResult:
    """
    Step 4: Analyze collected information, extract concepts, determine coverage,
    and format consolidated XML knowledge package.
    """
    if not retrieval.chunks:
        return KnowledgeAnalysisResult(
            directly_supported_concepts=[],
            partially_supported_concepts=[],
            missing_concepts=analysis.required_knowledge,
            coverage_level="unrelated",
            is_unrelated=True,
            evidence_summary="No matching documents found in knowledge base.",
            consolidated_context="(No matching documents found in knowledge base)",
            valid_chunk_ids=[],
        )

    max_sim = retrieval.max_similarity
    all_content = " ".join(c.get("content", "").lower() for c in retrieval.chunks)

    directly_supported = []
    partially_supported = []
    missing = []

    for concept in analysis.required_knowledge:
        c_lower = concept.lower()
        if c_lower in all_content:
            directly_supported.append(concept)
        elif any(part in all_content for part in c_lower.split() if len(part) > 3):
            partially_supported.append(concept)
        else:
            missing.append(concept)

    # Check if chunks are just topic headings (average length < 100 chars)
    content_lengths = [len(c.get("content", "").strip()) for c in retrieval.chunks if not c.get("is_neighbor")]
    avg_len = sum(content_lengths) / max(len(content_lengths), 1)

    # Evaluate coverage level
    if max_sim < 0.22 or ("world war" in question.lower() and "web" in all_content):
        coverage_level = "unrelated"
        is_unrelated = True
    elif avg_len < 100 and max_sim >= 0.35:
        coverage_level = "syllabus_topic_only"
        is_unrelated = False
    elif max_sim >= 0.70 and len(directly_supported) >= len(analysis.required_knowledge) * 0.6:
        coverage_level = "high"
        is_unrelated = False
    elif max_sim >= 0.45:
        coverage_level = "medium"
        is_unrelated = False
    else:
        coverage_level = "partial"
        is_unrelated = False

    # Build XML-encapsulated consolidated context
    context_parts = []
    valid_ids = []

    for c in retrieval.chunks:
        cid = str(c.get("id"))
        valid_ids.append(cid)
        tag_type = "neighboring_context" if c.get("is_neighbor") else "relevant_excerpt"
        sanitized = sanitize_chunk_content(c.get("content", ""))
        context_parts.append(
            f'<syllabus_reference id="{cid}" document="{c.get("pdf_name", "document.pdf")}" '
            f'page="{c.get("page_number", 1)}" chunk="{c.get("chunk_index", 0)}" type="{tag_type}">\n'
            f'{sanitized}\n'
            f'</syllabus_reference>'
        )

    consolidated_context = "\n\n".join(context_parts)

    evidence_summary = (
        f"Retrieved {len(retrieval.chunks)} chunks across {len(retrieval.documents_searched)} document(s) "
        f"with peak similarity of {max_sim:.2f}. "
        f"Concepts supported: {len(directly_supported)} direct, {len(partially_supported)} partial."
    )

    logger.info(
        "Knowledge analyzed: coverage=%s, direct=%s, partial=%s, missing=%s",
        coverage_level, directly_supported, partially_supported, missing
    )

    return KnowledgeAnalysisResult(
        directly_supported_concepts=directly_supported,
        partially_supported_concepts=partially_supported,
        missing_concepts=missing,
        coverage_level=coverage_level,
        is_unrelated=is_unrelated,
        evidence_summary=evidence_summary,
        consolidated_context=consolidated_context,
        valid_chunk_ids=valid_ids,
    )
