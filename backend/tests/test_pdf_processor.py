"""
Unit tests for PDF RAG Assistant - Phase 1.
Tests PDF processing, chunking, and token security.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set test environment variables before importing modules
os.environ.setdefault("SESSION_SECRET", "test-secret-key-for-testing-only")
os.environ.setdefault("CHUNK_SIZE", "500")
os.environ.setdefault("CHUNK_OVERLAP", "50")
os.environ.setdefault("MAX_UPLOAD_MB", "20")
os.environ.setdefault("MAX_PDF_PAGES", "200")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-service-role-key")
os.environ.setdefault("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
os.environ.setdefault("TOP_K", "4")
os.environ.setdefault("MIN_SIMILARITY", "0.0")

from services.pdf_processor import (
    PDFEmptyError,
    PDFExtractionError,
    PDFValidationError,
    chunk_text,
    extract_text_from_pdf,
    normalize_text,
    process_pdf,
    validate_pdf_file,
)
from utils.security import (
    TokenError,
    TokenExpiredError,
    TokenInvalidError,
    TokenMissingError,
    create_workspace_token,
    extract_token_from_header,
    verify_workspace_token,
)


class TestNormalizeText:
    """Tests for text normalization."""

    def test_empty_string(self):
        assert normalize_text("") == ""
        assert normalize_text(None) == ""

    def test_whitespace_normalization(self):
        text = "Hello    world\t\twith  spaces"
        result = normalize_text(text)
        assert "  " not in result
        assert "\t" not in result
        assert result == "Hello world with spaces"

    def test_paragraph_preservation(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        result = normalize_text(text)
        assert result == "Paragraph one.\n\nParagraph two.\n\nParagraph three."

    def test_single_newline_to_space(self):
        text = "Line one.\nLine two.\n\nNew paragraph."
        result = normalize_text(text)
        # Single newlines become spaces, double newlines preserved
        assert "Line one. Line two." in result
        assert "\n\nNew paragraph." in result

    def test_mixed_whitespace(self):
        text = "  Start  \n\n  Middle  \n  End  "
        result = normalize_text(text)
        assert result == "Start\n\nMiddle End"


class TestChunkText:
    """Tests for text chunking with overlap."""

    def test_empty_text(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_single_chunk(self):
        text = "This is a short text."
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_size_respected(self):
        text = "A" * 1000
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        # Should create multiple chunks
        assert len(chunks) >= 2
        # Each chunk should be approximately chunk_size (allowing for boundary adjustments)
        for chunk in chunks[:-1]:  # Last chunk can be shorter
            assert len(chunk) <= 550  # Some flexibility for boundary finding

    def test_overlap_present(self):
        text = "A" * 1000
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        # Check overlap between consecutive chunks
        for i in range(len(chunks) - 1):
            # The end of chunk i should overlap with start of chunk i+1
            end_of_i = chunks[i][-50:]
            start_of_next = chunks[i + 1][:50]
            assert end_of_i == start_of_next

    def test_forward_progress_no_infinite_loop(self):
        # Test with text that could cause boundary issues
        text = "A" * 100 + " " + "B" * 100 + " " + "C" * 100
        chunks = chunk_text(text, chunk_size=150, overlap=20)
        assert len(chunks) >= 2
        # Verify no duplicate chunks
        assert len(chunks) == len(set(chunks))

    def test_sentence_boundary_preference(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        chunks = chunk_text(text, chunk_size=50, overlap=10)
        # Should prefer sentence boundaries
        for chunk in chunks:
            # Chunks should end at sentence boundaries where possible
            assert chunk.endswith(".") or chunk == chunks[-1]

    def test_paragraph_boundary_preference(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        chunks = chunk_text(text, chunk_size=30, overlap=5)
        # Should prefer paragraph boundaries
        for chunk in chunks[:-1]:
            assert chunk.endswith(".") or "\n\n" in chunk

    def test_no_whitespace_only_chunks(self):
        text = "A" * 100 + "\n\n\n" + "B" * 100
        chunks = chunk_text(text, chunk_size=150, overlap=20)
        for chunk in chunks:
            assert chunk.strip() != ""


class TestValidatePDFFile:
    """Tests for PDF file validation."""

    def test_valid_pdf(self, tmp_path):
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%content")
        validate_pdf_file(str(pdf_path), 100, "test.pdf")

    def test_invalid_extension(self, tmp_path):
        pdf_path = tmp_path / "test.txt"
        pdf_path.write_bytes(b"%PDF-1.4\n%content")
        with pytest.raises(PDFValidationError) as exc:
            validate_pdf_file(str(pdf_path), 100, "test.txt")
        assert exc.value.code == "INVALID_FILE_TYPE"

    def test_file_too_large(self, tmp_path):
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%content")
        # Mock config to have small max size by patching MAX_UPLOAD_MB
        with patch("services.pdf_processor.config.MAX_UPLOAD_MB", 0.00005):  # ~50 bytes
            with pytest.raises(PDFValidationError) as exc:
                validate_pdf_file(str(pdf_path), 100, "test.pdf")
            assert exc.value.code == "FILE_TOO_LARGE"

    def test_invalid_pdf_signature(self, tmp_path):
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"NOT-PDF")
        with pytest.raises(PDFValidationError) as exc:
            validate_pdf_file(str(pdf_path), 100, "test.pdf")
        assert exc.value.code == "INVALID_PDF_SIGNATURE"


class TestExtractTextFromPDF:
    """Tests for PDF text extraction (mocked)."""

    def test_extract_text_mocked(self):
        # Create a mock PDF with known content
        mock_pages = [
            MagicMock(get_text=MagicMock(return_value="Page 1 content")),
            MagicMock(get_text=MagicMock(return_value="Page 2 content")),
        ]
        mock_doc = MagicMock()
        mock_doc.page_count = 2
        mock_doc.__getitem__ = MagicMock(side_effect=lambda i: mock_pages[i])
        mock_doc.close = MagicMock()

        with patch("fitz.open", return_value=mock_doc):
            pages = extract_text_from_pdf("fake.pdf")

        assert len(pages) == 2
        assert pages[0]["page_number"] == 1
        assert pages[0]["text"] == "Page 1 content"
        assert pages[1]["page_number"] == 2
        assert pages[1]["text"] == "Page 2 content"
        mock_doc.close.assert_called_once()

    def test_empty_pdf_raises_error(self):
        mock_doc = MagicMock()
        mock_doc.page_count = 0
        mock_doc.close = MagicMock()

        with patch("fitz.open", return_value=mock_doc):
            with pytest.raises(PDFEmptyError) as exc:
                extract_text_from_pdf("fake.pdf")
            assert exc.value.code == "EMPTY_PDF"

    def test_too_many_pages_raises_error(self):
        mock_doc = MagicMock()
        mock_doc.page_count = 201
        mock_doc.close = MagicMock()

        with patch("services.pdf_processor.config.MAX_PDF_PAGES", 200):
            with patch("fitz.open", return_value=mock_doc):
                with pytest.raises(PDFValidationError) as exc:
                    extract_text_from_pdf("fake.pdf")
                assert exc.value.code == "TOO_MANY_PAGES"

    def test_no_extractable_text_raises_error(self):
        mock_pages = [
            MagicMock(get_text=MagicMock(return_value="")),
            MagicMock(get_text=MagicMock(return_value="   ")),
        ]
        mock_doc = MagicMock()
        mock_doc.page_count = 2
        mock_doc.__getitem__ = MagicMock(side_effect=lambda i: mock_pages[i])
        mock_doc.close = MagicMock()

        with patch("fitz.open", return_value=mock_doc):
            with pytest.raises(PDFEmptyError) as exc:
                extract_text_from_pdf("fake.pdf")
            assert exc.value.code == "NO_EXTRACTABLE_TEXT"

    def test_pdf_open_failed_raises_error(self):
        with patch("fitz.open", side_effect=Exception("Cannot open")):
            with pytest.raises(PDFExtractionError) as exc:
                extract_text_from_pdf("fake.pdf")
            assert exc.value.code == "PDF_OPEN_FAILED"


class TestProcessPDF:
    """Tests for full PDF processing pipeline."""

    def test_process_pdf_mocked(self):
        # Create a mock file-like object
        mock_file = MagicMock()
        mock_file.seek = MagicMock()
        mock_file.tell = MagicMock(return_value=1000)
        mock_file.read = MagicMock(return_value=b"%PDF-1.4\n%content")

        # Mock the extraction
        mock_pages = [
            {"page_number": 1, "text": "This is page one content. " * 10},
            {"page_number": 2, "text": "This is page two content. " * 10},
        ]

        with patch("services.pdf_processor.validate_pdf_file"):
            with patch("services.pdf_processor.extract_text_from_pdf", return_value=mock_pages):
                with patch("services.pdf_processor.chunk_text") as mock_chunk:
                    mock_chunk.side_effect = lambda text, **kwargs: [text[:50], text[50:100]] if len(text) > 50 else [text]
                    result = process_pdf(mock_file, "test.pdf")

        assert "document_id" in result
        assert result["pdf_name"] == "test.pdf"
        assert result["pages_processed"] == 2
        assert result["chunks_created"] > 0
        assert result["status"] == "processed"
        assert len(result["chunks"]) == result["chunks_created"]

        # Verify chunk metadata
        for i, chunk in enumerate(result["chunks"]):
            assert "content" in chunk
            assert "metadata" in chunk
            assert chunk["metadata"]["pdf_name"] == "test.pdf"
            assert chunk["metadata"]["chunk_index"] == i
            assert chunk["metadata"]["page_number"] in [1, 2]

    def test_temp_file_cleanup_on_success(self):
        mock_file = MagicMock()
        mock_file.seek = MagicMock()
        mock_file.tell = MagicMock(return_value=1000)
        mock_file.read = MagicMock(return_value=b"%PDF-1.4\n%content")

        mock_pages = [{"page_number": 1, "text": "Content"}]

        with patch("services.pdf_processor.validate_pdf_file"):
            with patch("services.pdf_processor.extract_text_from_pdf", return_value=mock_pages):
                with patch("services.pdf_processor.chunk_text", return_value=["Content"]):
                    with patch("pathlib.Path.unlink") as mock_unlink:
                        process_pdf(mock_file, "test.pdf")
                        # Verify temp file cleanup was attempted
                        mock_unlink.assert_called()

    def test_temp_file_cleanup_on_error(self):
        mock_file = MagicMock()
        mock_file.seek = MagicMock()
        mock_file.tell = MagicMock(return_value=1000)
        mock_file.read = MagicMock(return_value=b"%PDF-1.4\n%content")

        with patch("services.pdf_processor.validate_pdf_file"):
            with patch("services.pdf_processor.extract_text_from_pdf", side_effect=PDFEmptyError("NO_TEXT", "No text")):
                with patch("pathlib.Path.unlink") as mock_unlink:
                    with pytest.raises(PDFEmptyError):
                        process_pdf(mock_file, "test.pdf")
                    # Verify temp file cleanup was attempted even on error
                    mock_unlink.assert_called()


class TestTokenSecurity:
    """Tests for workspace token creation and validation."""

    def test_create_workspace_token(self):
        token, workspace_id, expires_in = create_workspace_token()

        assert isinstance(token, str)
        assert len(token) > 0
        assert isinstance(workspace_id, str)
        # Validate UUID format
        import uuid
        uuid.UUID(workspace_id)
        assert expires_in > 0

    def test_verify_valid_token(self):
        token, workspace_id, _ = create_workspace_token()
        verified_id = verify_workspace_token(token)
        assert verified_id == workspace_id

    def test_verify_tampered_token(self):
        token, _, _ = create_workspace_token()
        # Tamper with the token
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(TokenInvalidError):
            verify_workspace_token(tampered)

    def test_verify_empty_token(self):
        with pytest.raises(TokenMissingError):
            verify_workspace_token("")

    def test_verify_none_token(self):
        with pytest.raises(TokenMissingError):
            verify_workspace_token(None)

    def test_token_payload_structure(self):
        token, workspace_id, _ = create_workspace_token()
        # Decode without verification to check payload
        from itsdangerous import TimedSerializer
        from utils.config import config
        serializer = TimedSerializer(config.SESSION_SECRET, salt="workspace-token")
        payload = serializer.loads(token)
        assert "workspace_id" in payload
        assert "iat" in payload
        assert payload["workspace_id"] == workspace_id

    def test_extract_token_from_header_valid(self):
        token = "test-token-123"
        auth_header = f"Bearer {token}"
        extracted = extract_token_from_header(auth_header)
        assert extracted == token

    def test_extract_token_from_header_missing(self):
        with pytest.raises(TokenMissingError):
            extract_token_from_header(None)

    def test_extract_token_from_header_invalid_format(self):
        with pytest.raises(TokenMissingError):
            extract_token_from_header("InvalidFormat")

    def test_extract_token_from_header_not_bearer(self):
        with pytest.raises(TokenMissingError):
            extract_token_from_header("Basic dXNlcjpwYXNz")


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_pdf_processing_flow(self):
        """Test the complete flow from file to chunks."""
        # This test uses a real small PDF if available, otherwise mocks
        mock_file = MagicMock()
        mock_file.seek = MagicMock()
        mock_file.tell = MagicMock(return_value=5000)
        mock_file.read = MagicMock(return_value=b"%PDF-1.4\n%content")

        mock_pages = [
            {"page_number": 1, "text": "This is the first page of the document. It contains some text." * 5},
            {"page_number": 2, "text": "This is the second page. More content here for testing." * 5},
        ]

        with patch("services.pdf_processor.validate_pdf_file"):
            with patch("services.pdf_processor.extract_text_from_pdf", return_value=mock_pages):
                result = process_pdf(mock_file, "integration-test.pdf")

        assert result["pages_processed"] == 2
        assert result["chunks_created"] > 0
        assert result["status"] == "processed"

        # Verify all chunks have correct metadata
        for chunk in result["chunks"]:
            assert "content" in chunk
            assert chunk["metadata"]["pdf_name"] == "integration-test.pdf"
            assert chunk["metadata"]["page_number"] in [1, 2]
            assert isinstance(chunk["metadata"]["chunk_index"], int)
            assert chunk["metadata"]["chunk_index"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
