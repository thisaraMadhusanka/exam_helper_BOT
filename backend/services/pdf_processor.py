"""
PDF text extraction and chunking for PDF RAG Assistant.
Uses PyMuPDF (fitz) for page-by-page text extraction with metadata preservation.
"""
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO, List, Dict, Any, Optional

import fitz  # PyMuPDF

from utils.config import config


class PDFProcessingError(Exception):
    """Base exception for PDF processing errors."""
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class PDFValidationError(PDFProcessingError):
    """PDF file validation failed."""
    pass


class PDFExtractionError(PDFProcessingError):
    """PDF text extraction failed."""
    pass


class PDFEmptyError(PDFProcessingError):
    """PDF has no extractable text (likely scanned/image-only)."""
    pass


def validate_pdf_file(file_path: str, file_size: int, pdf_name: str) -> None:
    """
    Validate PDF file before processing.

    Args:
        file_path: Path to the PDF file
        file_size: Size of the file in bytes
        pdf_name: Original filename

    Raises:
        PDFValidationError: If validation fails
    """
    # Check file extension
    if not pdf_name.lower().endswith(".pdf"):
        raise PDFValidationError("INVALID_FILE_TYPE", "File must be a PDF (.pdf extension)")

    # Check file size
    if file_size > config.max_upload_bytes:
        raise PDFValidationError(
            "FILE_TOO_LARGE",
            f"File size exceeds maximum allowed ({config.MAX_UPLOAD_MB} MB)"
        )

    # Check PDF magic bytes (signature)
    with open(file_path, "rb") as f:
        header = f.read(5)
        if header != b"%PDF-":
            raise PDFValidationError("INVALID_PDF_SIGNATURE", "File is not a valid PDF")


def extract_text_from_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract text from PDF page by page using PyMuPDF.

    Args:
        file_path: Path to the PDF file

    Returns:
        List of dicts with 'page_number' (1-based) and 'text' keys

    Raises:
        PDFExtractionError: If PDF cannot be opened or processed
        PDFEmptyError: If no extractable text found
    """
    pages = []

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise PDFExtractionError("PDF_OPEN_FAILED", f"Failed to open PDF: {str(e)}")

    try:
        # Check page count
        page_count = doc.page_count
        if page_count == 0:
            raise PDFEmptyError("EMPTY_PDF", "PDF has no pages")

        if page_count > config.MAX_PDF_PAGES:
            raise PDFValidationError(
                "TOO_MANY_PAGES",
                f"PDF has {page_count} pages, maximum allowed is {config.MAX_PDF_PAGES}"
            )

        # Extract text from each page
        total_text_length = 0
        for page_num in range(page_count):
            page = doc[page_num]
            # Use "text" mode for plain text extraction
            text = page.get_text("text")

            # Normalize whitespace but preserve paragraph structure
            text = normalize_text(text)

            if text.strip():
                total_text_length += len(text)

            pages.append({
                "page_number": page_num + 1,  # 1-based page numbers
                "text": text
            })

        # Check if any text was extracted
        if total_text_length == 0:
            raise PDFEmptyError(
                "NO_EXTRACTABLE_TEXT",
                "PDF appears to be scanned or image-only. OCR is not supported in this version."
            )

        return pages

    finally:
        doc.close()


def normalize_text(text: str) -> str:
    """
    Normalize whitespace while preserving paragraph boundaries.

    - Replace multiple spaces/tabs with single space
    - Preserve double newlines (paragraph breaks)
    - Normalize single newlines within paragraphs to spaces
    - Strip leading/trailing whitespace
    """
    if not text:
        return ""

    # Replace tabs with spaces
    text = text.replace("\t", " ")

    # Normalize multiple spaces to single space (but not newlines)
    text = re.sub(r"[ ]{2,}", " ", text)

    # Split by double newline to preserve paragraphs
    paragraphs = text.split("\n\n")
    normalized_paragraphs = []

    for para in paragraphs:
        # Within paragraph, replace single newlines with spaces
        para = para.replace("\n", " ")
        # Normalize spaces again
        para = re.sub(r"[ ]{2,}", " ", para)
        para = para.strip()
        if para:
            normalized_paragraphs.append(para)

    # Join with double newline to preserve paragraph boundaries
    return "\n\n".join(normalized_paragraphs)


def chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
    """
    Split text into chunks with overlap, preferring sentence/paragraph boundaries.

    Args:
        text: Text to chunk
        chunk_size: Target chunk size in characters (default from config)
        overlap: Overlap between chunks in characters (default from config)

    Returns:
        List of text chunks
    """
    if chunk_size is None:
        chunk_size = config.CHUNK_SIZE
    if overlap is None:
        overlap = config.CHUNK_OVERLAP

    if not text or not text.strip():
        return []

    # If text is shorter than chunk_size, return as single chunk without modification
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        # Calculate end position
        end = min(start + chunk_size, text_len)

        # If we're not at the end, try to find a good boundary
        if end < text_len:
            # Try to find paragraph boundary (double newline) first
            boundary = text.rfind("\n\n", start, end)
            if boundary == -1 or boundary <= start:
                # Try sentence boundary (period, question, exclamation followed by space)
                boundary = max(
                    text.rfind(". ", start, end),
                    text.rfind("? ", start, end),
                    text.rfind("! ", start, end)
                )
            if boundary == -1 or boundary <= start:
                # Try any whitespace boundary
                boundary = text.rfind(" ", start, end)

            # If we found a good boundary, use it (include the boundary char)
            if boundary > start:
                end = boundary + 1

        chunk = text[start:end]

        # Only add non-empty chunks
        if chunk.strip():
            chunks.append(chunk)

        # If we've reached the end of the text, break
        if end >= text_len:
            break

        # Move start forward, accounting for overlap
        # Ensure we always make forward progress
        next_start = end - overlap
        if next_start <= start:
            next_start = start + 1
        start = next_start

    return chunks


def process_pdf(file: BinaryIO, pdf_name: str) -> Dict[str, Any]:
    """
    Process a PDF file: validate, extract text, create chunks with metadata.

    Args:
        file: File-like object (e.g., FastAPI UploadFile.file)
        pdf_name: Original filename

    Returns:
        Dict with:
        - document_id: Unique identifier for this document
        - pdf_name: Original filename
        - pages_processed: Number of pages processed
        - chunks_created: Number of chunks created
        - chunks: List of chunk dicts with content and metadata
        - status: "processed"

    Raises:
        PDFValidationError: If file validation fails
        PDFExtractionError: If text extraction fails
        PDFEmptyError: If no text could be extracted
    """
    # Generate document ID
    document_id = str(uuid.uuid4())

    # Get file size by seeking
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    # Create a unique temporary file
    temp_dir = Path(tempfile.gettempdir())
    temp_filename = f"pdf_rag_{uuid.uuid4().hex}.pdf"
    temp_path = temp_dir / temp_filename

    try:
        # Write uploaded file to temp location
        with open(temp_path, "wb") as f:
            content = file.read()
            f.write(content)

        # Validate the PDF
        validate_pdf_file(str(temp_path), file_size, pdf_name)

        # Extract text page by page
        pages = extract_text_from_pdf(str(temp_path))
        pages_processed = len(pages)

        # Chunk each page independently to preserve page provenance
        all_chunks = []
        chunk_index = 0

        for page in pages:
            page_chunks = chunk_text(page["text"])

            for chunk_text_content in page_chunks:
                if chunk_text_content.strip():  # Skip empty chunks
                    all_chunks.append({
                        "content": chunk_text_content,
                        "metadata": {
                            "page_number": page["page_number"],
                            "chunk_index": chunk_index,
                            "pdf_name": pdf_name
                        }
                    })
                    chunk_index += 1

        chunks_created = len(all_chunks)

        if chunks_created == 0:
            raise PDFEmptyError(
                "NO_CHUNKS_CREATED",
                "PDF processed but no valid text chunks were created"
            )

        return {
            "document_id": document_id,
            "pdf_name": pdf_name,
            "pages_processed": pages_processed,
            "chunks_created": chunks_created,
            "chunks": all_chunks,
            "status": "processed"
        }

    finally:
        # Always clean up temp file
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            # Best effort cleanup - don't fail the request if cleanup fails
            pass


def print_first_chunks(chunks: List[Dict[str, Any]], count: int = 3) -> None:
    """Print first N chunks for local development debugging."""
    print(f"\n=== First {min(count, len(chunks))} chunks (debug output) ===")
    for i, chunk in enumerate(chunks[:count]):
        meta = chunk["metadata"]
        content_preview = chunk["content"][:200] + ("..." if len(chunk["content"]) > 200 else "")
        print(f"Chunk {i+1}: page={meta['page_number']}, index={meta['chunk_index']}")
        print(f"  Content: {content_preview}")
    print("=" * 50)