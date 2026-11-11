"""
Lesson service for PDF RAG Assistant.
Handles lesson management, metadata, and document association.
Supports local JSON persistence and Supabase integration.
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from utils.config import config
from services.vector_store import get_supabase_client, delete_document

logger = logging.getLogger(__name__)

# Shared workspace ID used for lesson knowledge bases so any student can query them
SHARED_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LESSONS_FILE = DATA_DIR / "lessons.json"


def _ensure_data_dir() -> None:
    """Ensure data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_local_lessons() -> list[dict[str, Any]]:
    """Load lessons from local JSON file."""
    _ensure_data_dir()
    if not LESSONS_FILE.exists():
        return []
    try:
        with open(LESSONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to read local lessons file: %s", e)
        return []


def _save_local_lessons(lessons: list[dict[str, Any]]) -> None:
    """Save lessons to local JSON file."""
    _ensure_data_dir()
    try:
        with open(LESSONS_FILE, "w", encoding="utf-8") as f:
            json.dump(lessons, f, indent=2, default=str)
    except Exception as e:
        logger.error("Failed to save local lessons file: %s", e)


def _normalise_lesson(lesson: dict[str, Any]) -> dict[str, Any]:
    """Expose legacy single-document lessons through the multi-document shape."""
    normalized = dict(lesson)
    documents = normalized.get("documents")
    if not isinstance(documents, list):
        documents = []

    if not documents and normalized.get("document_id"):
        documents = [{
            "document_id": str(normalized["document_id"]),
            "pdf_name": normalized.get("pdf_name") or "document.pdf",
            "pages_count": normalized.get("pages_count", 0) or 0,
            "chunks_count": normalized.get("chunks_count", 0) or 0,
        }]

    normalized["documents"] = documents
    return normalized


def list_lessons() -> list[dict[str, Any]]:
    """
    List all lessons.
    Attempts to read from Supabase if table exists, otherwise loads from local storage.
    """
    # Try Supabase if configured
    if config.SUPABASE_URL and config.SUPABASE_KEY:
        try:
            client = get_supabase_client()
            res = client.table("lessons").select("*").order("created_at", desc=False).execute()
            if res.data is not None:
                return [_normalise_lesson(lesson) for lesson in res.data]
        except Exception as e:
            logger.info("Supabase lessons table not accessible, using local storage: %s", e)

    return [_normalise_lesson(lesson) for lesson in _load_local_lessons()]


def get_lesson(lesson_id: str) -> Optional[dict[str, Any]]:
    """Get a lesson by its ID."""
    lessons = list_lessons()
    for l in lessons:
        if str(l.get("id")) == str(lesson_id):
            return l
    return None


def create_lesson(title: str, description: Optional[str] = None) -> dict[str, Any]:
    """
    Create a new lesson without a document yet.
    """
    lesson_id = str(uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    new_lesson = {
        "id": lesson_id,
        "title": title.strip(),
        "description": (description or "").strip(),
        "workspace_id": SHARED_WORKSPACE_ID,
        "document_id": None,
        "pdf_name": None,
        "pages_count": 0,
        "chunks_count": 0,
        "documents": [],
        "created_at": now_iso,
    }

    # Save to local
    lessons = list_lessons()
    lessons.append(new_lesson)
    _save_local_lessons(lessons)

    # Try saving to Supabase if configured
    if config.SUPABASE_URL and config.SUPABASE_KEY:
        try:
            client = get_supabase_client()
            client.table("lessons").insert(new_lesson).execute()
        except Exception as e:
            logger.info("Supabase insert lesson skipped or failed: %s", e)

    return new_lesson


def attach_document_to_lesson(
    lesson_id: str,
    document_id: str,
    pdf_name: str,
    pages_count: int,
    chunks_count: int,
) -> Optional[dict[str, Any]]:
    """
    Attach an uploaded PDF document and chunk stats to a lesson.
    """
    lessons = list_lessons()
    target_lesson = None

    for index, l in enumerate(lessons):
        if str(l.get("id")) == str(lesson_id):
            l = _normalise_lesson(l)
            documents = l["documents"]
            document = {
                "document_id": str(document_id),
                "pdf_name": pdf_name,
                "pages_count": pages_count,
                "chunks_count": chunks_count,
            }
            existing_index = next(
                (index for index, item in enumerate(documents)
                 if str(item.get("document_id")) == str(document_id)),
                None,
            )
            if existing_index is None:
                documents.append(document)
            else:
                documents[existing_index] = document

            l["documents"] = documents
            latest = documents[-1] if documents else None
            l["document_id"] = latest.get("document_id") if latest else None
            l["pdf_name"] = latest.get("pdf_name") if latest else None
            l["pages_count"] = sum(int(item.get("pages_count", 0) or 0) for item in documents)
            l["chunks_count"] = sum(int(item.get("chunks_count", 0) or 0) for item in documents)
            l["workspace_id"] = SHARED_WORKSPACE_ID
            lessons[index] = l
            target_lesson = l
            break

    if target_lesson:
        _save_local_lessons(lessons)

        # Try update Supabase if configured
        if config.SUPABASE_URL and config.SUPABASE_KEY:
            try:
                client = get_supabase_client()
                client.table("lessons").update({
                    "documents": target_lesson["documents"],
                    "document_id": target_lesson["document_id"],
                    "pdf_name": target_lesson["pdf_name"],
                    "pages_count": target_lesson["pages_count"],
                    "chunks_count": target_lesson["chunks_count"],
                    "workspace_id": SHARED_WORKSPACE_ID,
                }).eq("id", lesson_id).execute()
            except Exception as e:
                logger.info("Supabase update lesson skipped: %s", e)

    return target_lesson


def remove_document_from_lesson(lesson_id: str, document_id: str) -> Optional[dict[str, Any]]:
    """Detach one PDF from a lesson and return the updated lesson."""
    lessons = list_lessons()
    target_lesson = None

    for index, lesson in enumerate(lessons):
        if str(lesson.get("id")) != str(lesson_id):
            continue

        normalized = _normalise_lesson(lesson)
        remaining = [
            item for item in normalized["documents"]
            if str(item.get("document_id")) != str(document_id)
        ]
        if len(remaining) == len(normalized["documents"]):
            return None

        normalized["documents"] = remaining
        latest = remaining[-1] if remaining else None
        normalized["document_id"] = latest.get("document_id") if latest else None
        normalized["pdf_name"] = latest.get("pdf_name") if latest else None
        normalized["pages_count"] = sum(int(item.get("pages_count", 0) or 0) for item in remaining)
        normalized["chunks_count"] = sum(int(item.get("chunks_count", 0) or 0) for item in remaining)
        normalized["workspace_id"] = normalized.get("workspace_id", SHARED_WORKSPACE_ID)
        lessons[index] = normalized
        target_lesson = normalized
        break

    if target_lesson is None:
        return None

    _save_local_lessons(lessons)
    if config.SUPABASE_URL and config.SUPABASE_KEY:
        try:
            client = get_supabase_client()
            client.table("lessons").update({
                "documents": target_lesson["documents"],
                "document_id": target_lesson["document_id"],
                "pdf_name": target_lesson["pdf_name"],
                "pages_count": target_lesson["pages_count"],
                "chunks_count": target_lesson["chunks_count"],
            }).eq("id", lesson_id).execute()
        except Exception as e:
            logger.info("Supabase lesson document detach skipped: %s", e)

    return target_lesson


def detach_document_from_all_lessons(document_id: str) -> list[str]:
    """
    Detach a document from all lessons that reference it.
    Updates both local JSON storage and Supabase database.
    Returns the list of affected lesson IDs.
    """
    lessons = list_lessons()
    affected_ids = []
    doc_id_str = str(document_id)

    for index, lesson in enumerate(lessons):
        norm = _normalise_lesson(lesson)
        original_docs = norm.get("documents", [])
        remaining = [d for d in original_docs if str(d.get("document_id")) != doc_id_str]
        had_legacy = str(norm.get("document_id")) == doc_id_str

        if len(remaining) != len(original_docs) or had_legacy:
            affected_ids.append(str(norm["id"]))
            norm["documents"] = remaining
            latest = remaining[-1] if remaining else None
            norm["document_id"] = latest.get("document_id") if latest else None
            norm["pdf_name"] = latest.get("pdf_name") if latest else None
            norm["pages_count"] = sum(int(item.get("pages_count", 0) or 0) for item in remaining)
            norm["chunks_count"] = sum(int(item.get("chunks_count", 0) or 0) for item in remaining)
            norm["workspace_id"] = norm.get("workspace_id", SHARED_WORKSPACE_ID)
            lessons[index] = norm

            if config.SUPABASE_URL and config.SUPABASE_KEY:
                try:
                    client = get_supabase_client()
                    client.table("lessons").update({
                        "documents": norm["documents"],
                        "document_id": norm["document_id"],
                        "pdf_name": norm["pdf_name"],
                        "pages_count": norm["pages_count"],
                        "chunks_count": norm["chunks_count"],
                    }).eq("id", norm["id"]).execute()
                except Exception as e:
                    logger.warning("Failed to update Supabase lesson %s when detaching document %s: %s", norm["id"], document_id, e)

    if affected_ids:
        _save_local_lessons(lessons)

    return affected_ids


def delete_lesson(lesson_id: str) -> bool:
    """
    Delete a lesson and its associated document chunks from pgvector.
    """
    lessons = list_lessons()
    target_lesson = None
    remaining = []

    for l in lessons:
        if str(l.get("id")) == str(lesson_id):
            target_lesson = l
        else:
            remaining.append(l)

    if not target_lesson:
        return False

    _save_local_lessons(remaining)

    # Delete chunks from Supabase if document_id exists
    document_ids = {
        str(item.get("document_id"))
        for item in _normalise_lesson(target_lesson)["documents"]
        if item.get("document_id")
    }
    if target_lesson.get("document_id"):
        document_ids.add(str(target_lesson["document_id"]))
    workspace_id = target_lesson.get("workspace_id", SHARED_WORKSPACE_ID)
    for document_id in document_ids:
        try:
            delete_document(workspace_id=workspace_id, document_id=document_id)
        except Exception as e:
            logger.warning("Failed to delete chunks for lesson %s: %s", lesson_id, e)

    if config.SUPABASE_URL and config.SUPABASE_KEY:
        try:
            client = get_supabase_client()
            client.table("lessons").delete().eq("id", lesson_id).execute()
        except Exception as e:
            logger.info("Supabase delete lesson skipped: %s", e)

    return True
