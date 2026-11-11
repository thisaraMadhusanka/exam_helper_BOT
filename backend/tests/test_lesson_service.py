"""Unit tests for Lesson Service and Admin Authentication."""

import pytest
import services.lesson_service as lesson_service
from utils.admin_auth import (
    create_admin_token,
    verify_admin_credentials,
    verify_admin_token,
)
from utils.config import config
from utils.security import TokenError, TokenInvalidError
from services.lesson_service import (
    create_lesson,
    get_lesson,
    list_lessons,
    attach_document_to_lesson,
    delete_lesson,
)


def test_admin_credentials_verification(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "test-password")

    assert verify_admin_credentials(" ADMIN@example.com ", "test-password") is True
    assert verify_admin_credentials("other@example.com", "test-password") is False
    assert verify_admin_credentials("admin@example.com", "wrong-password") is False
    assert verify_admin_credentials("", "test-password") is False


def test_admin_credentials_are_rejected_when_not_configured(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_EMAIL", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")

    assert verify_admin_credentials("admin@example.com", "test-password") is False


def test_admin_token_roundtrip():
    token, expires_in = create_admin_token(expires_in_hours=1)
    assert token is not None
    assert expires_in == 3600
    assert verify_admin_token(token) is True


def test_admin_token_invalid():
    with pytest.raises(TokenError):
        verify_admin_token("invalid.token.signature")


def test_lesson_crud_flow():
    # Create lesson
    lesson = create_lesson(
        title="Test Lesson 101",
        description="Introductory test lesson",
    )
    assert lesson["id"] is not None
    assert lesson["title"] == "Test Lesson 101"
    assert lesson["document_id"] is None

    # Retrieve lesson
    fetched = get_lesson(lesson["id"])
    assert fetched is not None
    assert fetched["title"] == "Test Lesson 101"

    # Attach document
    updated = attach_document_to_lesson(
        lesson_id=lesson["id"],
        document_id="11111111-1111-1111-1111-111111111111",
        pdf_name="sample_test.pdf",
        pages_count=5,
        chunks_count=12,
    )
    assert updated is not None
    assert updated["document_id"] == "11111111-1111-1111-1111-111111111111"
    assert updated["pdf_name"] == "sample_test.pdf"
    assert updated["chunks_count"] == 12

    # Verify in list
    all_lessons = list_lessons()
    assert any(l["id"] == lesson["id"] for l in all_lessons)

    # Delete lesson
    deleted = delete_lesson(lesson["id"])
    assert deleted is True
    assert get_lesson(lesson["id"]) is None


def test_lesson_supports_multiple_pdfs_and_individual_removal(tmp_path, monkeypatch):
    monkeypatch.setattr(lesson_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(lesson_service, "LESSONS_FILE", tmp_path / "lessons.json")
    monkeypatch.setattr(lesson_service.config, "SUPABASE_URL", None)
    monkeypatch.setattr(lesson_service.config, "SUPABASE_KEY", None)

    lesson = create_lesson("Multiple PDF lesson")
    first = attach_document_to_lesson(
        lesson["id"], "doc-1", "part-one.pdf", pages_count=2, chunks_count=3
    )
    second = attach_document_to_lesson(
        lesson["id"], "doc-2", "part-two.pdf", pages_count=4, chunks_count=5
    )

    assert first is not None
    assert second is not None
    assert [item["document_id"] for item in second["documents"]] == ["doc-1", "doc-2"]
    assert second["pages_count"] == 6
    assert second["chunks_count"] == 8

    updated = lesson_service.remove_document_from_lesson(lesson["id"], "doc-1")
    assert updated is not None
    assert [item["document_id"] for item in updated["documents"]] == ["doc-2"]
    assert updated["document_id"] == "doc-2"
    assert updated["pages_count"] == 4
    assert lesson_service.remove_document_from_lesson(lesson["id"], "missing") is None


def test_legacy_lesson_is_exposed_as_single_document():
    legacy = {
        "id": "lesson-legacy",
        "document_id": "doc-old",
        "pdf_name": "legacy.pdf",
        "pages_count": 7,
        "chunks_count": 9,
    }

    normalized = lesson_service._normalise_lesson(legacy)

    assert normalized["documents"] == [{
        "document_id": "doc-old",
        "pdf_name": "legacy.pdf",
        "pages_count": 7,
        "chunks_count": 9,
    }]


def test_deleting_lesson_removes_all_attached_documents(tmp_path, monkeypatch):
    monkeypatch.setattr(lesson_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(lesson_service, "LESSONS_FILE", tmp_path / "lessons.json")
    monkeypatch.setattr(lesson_service.config, "SUPABASE_URL", None)
    monkeypatch.setattr(lesson_service.config, "SUPABASE_KEY", None)
    deleted = []
    monkeypatch.setattr(
        lesson_service,
        "delete_document",
        lambda workspace_id, document_id: deleted.append(document_id),
    )

    lesson = create_lesson("Delete all associated PDFs")
    attach_document_to_lesson(lesson["id"], "doc-1", "one.pdf", 1, 1)
    attach_document_to_lesson(lesson["id"], "doc-2", "two.pdf", 2, 2)

    assert delete_lesson(lesson["id"]) is True
    assert set(deleted) == {"doc-1", "doc-2"}


def test_detach_document_from_all_lessons(tmp_path, monkeypatch):
    monkeypatch.setattr(lesson_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(lesson_service, "LESSONS_FILE", tmp_path / "lessons.json")
    monkeypatch.setattr(lesson_service.config, "SUPABASE_URL", None)
    monkeypatch.setattr(lesson_service.config, "SUPABASE_KEY", None)

    lesson1 = create_lesson("Lesson 1")
    lesson2 = create_lesson("Lesson 2")
    attach_document_to_lesson(lesson1["id"], "shared-doc", "shared.pdf", 5, 10)
    attach_document_to_lesson(lesson1["id"], "doc-unique", "unique.pdf", 2, 4)
    attach_document_to_lesson(lesson2["id"], "shared-doc", "shared.pdf", 5, 10)

    affected = lesson_service.detach_document_from_all_lessons("shared-doc")
    assert set(affected) == {lesson1["id"], lesson2["id"]}

    l1 = get_lesson(lesson1["id"])
    l2 = get_lesson(lesson2["id"])
    assert [d["document_id"] for d in l1["documents"]] == ["doc-unique"]
    assert l1["chunks_count"] == 4
    assert len(l2["documents"]) == 0
    assert l2["chunks_count"] == 0
