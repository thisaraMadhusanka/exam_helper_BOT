"""
PDF RAG Assistant - FastAPI Backend
Phase 1: PDF extraction, session management, and upload endpoint.
Phase 2: Vector embeddings, Supabase/pgvector storage, similarity search.
Phase 3: RAG with citations, evidence threshold, Groq/OpenRouter fallback, AI thinking analysis.
Enhancement: Admin portal, Lesson management, direct knowledge base upload, and student Q&A.
"""
import base64
import binascii
import logging
import re
from contextlib import asynccontextmanager
from typing import Optional, Any
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from utils.config import config, validate_required_config
from utils.security import (
    TokenError,
    TokenExpiredError,
    TokenInvalidError,
    TokenMissingError,
    create_workspace_token,
    extract_token_from_header,
    verify_workspace_token,
)
from utils.admin_auth import (
    create_admin_token,
    verify_admin_code,
    verify_admin_credentials,
    verify_admin_token,
)
from services.pdf_processor import (
    PDFEmptyError,
    PDFExtractionError,
    PDFProcessingError,
    PDFValidationError,
    process_pdf,
    print_first_chunks,
)
from services.vector_store import (
    EmbeddingError,
    VectorStoreConnectionError,
    VectorStoreOperationError,
    generate_embeddings_on_zero_gpu,
    search_similar_chunks,
    delete_document,
    store_chunks,
    list_documents,
)
from services.rag_service import (
    RAGError,
    LLMError,
    EvidenceThresholdError,
    CitationValidationError,
    generate_answer,
    generate_answer_stream,
    RAGResponse,
)
from services.lesson_service import (
    SHARED_WORKSPACE_ID,
    list_lessons,
    get_lesson,
    create_lesson,
    attach_document_to_lesson,
    remove_document_from_lesson,
    detach_document_from_all_lessons,
    delete_lesson,
    _normalise_lesson,
)
from services.promo_service import (
    create_signed_promo_token,
    generate_referral_code,
    list_promo_codes,
    get_promo_code_by_code,
    get_promo_code_by_id,
    create_promo_code,
    toggle_promo_code_status,
    delete_promo_code,
    verify_and_redeem_promo_code,
    verify_signed_promo_token,
    get_promo_stats,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    missing = validate_required_config()
    if missing:
        logger.warning("Missing configuration (some features may not work): %s", missing)
    else:
        logger.info("All required configuration present")

    logger.info("PDF RAG Assistant backend starting up on port %d", config.PORT)
    yield
    logger.info("PDF RAG Assistant backend shutting down")


app = FastAPI(
    title="PDF RAG Assistant API",
    description="Backend API for PDF RAG Assistant with Admin Lesson Management and Student Q&A",
    version="1.2.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for request/response
class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UploadResponse(BaseModel):
    document_id: str
    pdf_name: str
    pages_processed: int
    chunks_created: int
    status: str


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    document_id: Optional[str] = Field(None, description="Document ID to search within")
    top_k: Optional[int] = Field(None, ge=1, le=20, description="Number of results to return")


class SearchResult(BaseModel):
    id: str
    document_id: str
    pdf_name: str
    content: str
    metadata: dict
    page_number: int
    chunk_index: int
    similarity: float


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query: str
    document_id: Optional[str]
    count: int


class DeleteResponse(BaseModel):
    document_id: str
    chunks_deleted: int
    status: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Question to ask")
    document_ids: Optional[list[str]] = Field(None, description="Document IDs to query")
    document_id: Optional[str] = Field(None, description="Single document ID to query")
    lesson_id: Optional[str] = Field(None, description="Lesson ID to query")
    marks: Optional[int] = Field(None, ge=1, le=100, description="Allocated marks for the question")
    answer_style: Optional[str] = Field("exam", description="Format style: exam, concise, detailed")
    top_k: Optional[int] = Field(None, ge=1, le=20, description="Number of chunks to retrieve")
    min_similarity: Optional[float] = Field(None, ge=0.0, le=1.0, description="Minimum similarity threshold")
    images: list[str] = Field(default_factory=list, description="Image data URLs for visual analysis")

    @field_validator("images")
    @classmethod
    def limit_image_count(cls, images: list[str]) -> list[str]:
        if len(images) > 3:
            raise ValueError("Attach up to 3 images per message.")
        return images


class QuestionAnalysisModel(BaseModel):
    topic: str
    subtopic: str
    question_type: str
    intent: str


class ThinkingSummaryModel(BaseModel):
    question_understanding: str
    retrieval_summary: str
    evidence_analysis: str
    reasoning_summary: str
    additional_knowledge_used: bool


class SourceInfo(BaseModel):
    document_name: str
    page_number: int
    chunk_index: int
    excerpt: str
    support_type: str = "direct"
    chunk_id: Optional[str] = None
    pdf_name: Optional[str] = None
    similarity: Optional[float] = None
    cited: bool = True
    lesson_name: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    question_analysis: Optional[QuestionAnalysisModel] = None
    thinking_summary: Optional[ThinkingSummaryModel] = None
    sources: list[SourceInfo]
    answer_status: str = "completed"
    knowledge_coverage: str = "high"
    question_type: str = "explanation"
    reasoning_status: str = "completed"
    additional_knowledge_used: bool = False
    abstained: bool = False
    thinking: Optional[str] = ""


# Admin & Lesson models
class AdminCodeLoginRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=100, description="Admin secret access code")


class AdminLoginRequest(BaseModel):
    email: Optional[str] = Field(None, max_length=320, description="Admin email address")
    password: Optional[str] = Field(None, description="Admin secret password")
    code: Optional[str] = Field(None, max_length=100, description="Admin secret access code")


class AdminLoginResponse(BaseModel):
    access_token: str
    role: str = "admin"
    username: str
    expires_in: int


class LessonCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Title of the lesson")
    description: Optional[str] = Field("", max_length=1000, description="Brief description")


class LessonResponse(BaseModel):
    id: str
    title: str
    description: str
    document_id: Optional[str] = None
    pdf_name: Optional[str] = None
    pages_count: int = 0
    chunks_count: int = 0
    documents: list[dict] = Field(default_factory=list)
    created_at: str


class KnowledgeDocumentResponse(BaseModel):
    document_id: str
    workspace_id: str
    pdf_name: str
    pages_count: int
    chunks_count: int
    created_at: str = ""
    lesson_id: Optional[str] = None
    lesson_title: Optional[str] = None


class PromoVerifyRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, description="Promo or referral code")


class PromoVerifyResponse(BaseModel):
    valid: bool
    promo_token: Optional[str] = None
    admin_token: Optional[str] = None
    is_admin: bool = False
    code: Optional[str] = None
    label: Optional[str] = None
    message: str


class PromoTokenCheckResponse(BaseModel):
    valid: bool
    code: Optional[str] = None
    label: Optional[str] = None


class AdminPromoCreateRequest(BaseModel):
    code: Optional[str] = Field(None, max_length=50, description="Custom promo code, e.g. ALEX123")
    prefix: Optional[str] = Field(None, max_length=30, description="Username or prefix for generator, e.g. Alex Jones or REF")
    length: Optional[int] = Field(4, ge=2, le=12, description="Random suffix length")
    label: Optional[str] = Field(None, max_length=200, description="Optional label or student name")
    max_uses: Optional[int] = Field(None, ge=1, description="Maximum usage limit, null for unlimited")


class PromoCodeItemResponse(BaseModel):
    id: str
    code: str
    label: str = ""
    max_uses: Optional[int] = None
    used_count: int = 0
    is_active: bool = True
    created_at: str
    created_by: str = "admin"
    last_used_at: Optional[str] = None


class AdminPromoListResponse(BaseModel):
    codes: list[PromoCodeItemResponse]
    stats: dict[str, Any]


def lesson_response(lesson: dict) -> LessonResponse:
    """Build the public lesson shape while retaining legacy summary fields."""
    return LessonResponse(
        id=str(lesson["id"]),
        title=lesson["title"],
        description=lesson.get("description", "") or "",
        document_id=str(lesson["document_id"]) if lesson.get("document_id") else None,
        pdf_name=lesson.get("pdf_name"),
        pages_count=lesson.get("pages_count", 0) or 0,
        chunks_count=lesson.get("chunks_count", 0) or 0,
        documents=lesson.get("documents", []),
        created_at=str(lesson.get("created_at", "")),
    )


def validate_image_data_urls(images: list[str]) -> list[str]:
    """Validate bounded base64 image uploads before sending them to an LLM."""
    if len(images) > 3:
        raise ValueError("Attach up to 3 images per message.")

    validated = []
    signatures = {
        "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
        "image/webp": lambda data: data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }

    for image in images:
        match = re.fullmatch(r"data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/]*={0,2})", image)
        if not match:
            raise ValueError("Images must be valid PNG, JPEG, or WebP data URLs.")

        media_type, encoded = match.groups()
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("An attached image is not valid base64 data.") from error

        if not image_bytes or len(image_bytes) > 5 * 1024 * 1024:
            raise ValueError("Each image must be smaller than 5MB.")
        if not signatures[media_type](image_bytes):
            raise ValueError(f"The attached file does not contain a valid {media_type} image.")
        validated.append(image)

    return validated


def create_error_response(code: str, message: str, status_code: int = 400) -> JSONResponse:
    """Create standardized error response."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}}
    )


def get_workspace_id_from_request(request: Request) -> str:
    """Extract and verify workspace token from request."""
    auth_header = request.headers.get("Authorization")
    try:
        token = extract_token_from_header(auth_header)
        workspace_id = verify_workspace_token(token)
        return workspace_id
    except TokenMissingError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": e.code, "message": e.message}}
        )
    except (TokenExpiredError, TokenInvalidError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": e.code, "message": e.message}}
        )


def require_admin(request: Request) -> bool:
    """Verify that the request has a valid Admin authorization token."""
    auth_header = request.headers.get("Authorization")
    try:
        token = extract_token_from_header(auth_header)
        verify_admin_token(token)
        return True
    except TokenMissingError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "ADMIN_TOKEN_MISSING", "message": "Admin authorization required"}}
        )
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "ADMIN_TOKEN_EXPIRED", "message": "Admin session expired. Please log in again."}}
        )
    except TokenInvalidError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "ADMIN_ACCESS_DENIED", "message": "Invalid admin token or insufficient permissions"}}
        )


def require_promo_or_admin_access(request: Request) -> str:
    """
    Ensure the user has verified a promo code or is an authenticated admin.
    Blocks any access if unverified or tampered.
    """
    # 1. Admin bypass
    auth_header = request.headers.get("Authorization")
    if auth_header:
        try:
            admin_token = extract_token_from_header(auth_header)
            verify_admin_token(admin_token)
            return "admin"
        except Exception:
            pass

    # 2. X-Promo-Token
    promo_token = request.headers.get("X-Promo-Token")
    if promo_token:
        valid_code = verify_signed_promo_token(promo_token)
        if valid_code:
            return valid_code

    # 3. X-Promo-Code direct header
    promo_code = request.headers.get("X-Promo-Code")
    if promo_code:
        record = get_promo_code_by_code(promo_code)
        if record and record.get("is_active", True):
            return record.get("code", promo_code.strip().upper())

    # 4. Check Bearer token as promo token
    if auth_header:
        try:
            token = extract_token_from_header(auth_header)
            valid_code = verify_signed_promo_token(token)
            if valid_code:
                return valid_code
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": {"code": "PROMO_CODE_REQUIRED", "message": "Promo code verification required. Please enter a valid promo code to unlock chat."}}
    )


# ============================================================================
# Basic & Session Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "port": config.PORT}


@app.post("/session", response_model=SessionResponse)
async def create_session():
    """Create a new anonymous workspace session."""
    try:
        token, workspace_id, expires_in = create_workspace_token()
        logger.info("Created new workspace session: %s", workspace_id)
        return SessionResponse(
            access_token=token,
            token_type="bearer",
            expires_in=expires_in
        )
    except RuntimeError as e:
        logger.error("Failed to create session: %s", e)
        return create_error_response(
            "SESSION_CREATION_FAILED",
            "Unable to create session. Server configuration error.",
            status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ============================================================================
# Admin Authentication Endpoints
# ============================================================================

@app.post("/admin/login-code", response_model=AdminLoginResponse)
async def admin_code_login(login_request: AdminCodeLoginRequest):
    """Authenticate as Admin using the single Admin Access Code."""
    if not verify_admin_code(login_request.code):
        logger.warning("Failed admin code login attempt")
        return create_error_response(
            "INVALID_ADMIN_CODE",
            "Invalid admin access code",
            status.HTTP_401_UNAUTHORIZED,
        )

    token, expires_in = create_admin_token()
    logger.info("Admin code login successful")
    return AdminLoginResponse(
        access_token=token,
        role="admin",
        username=config.ADMIN_USERNAME,
        expires_in=expires_in,
    )


@app.post("/admin/login", response_model=AdminLoginResponse)
async def admin_login(login_request: AdminLoginRequest):
    """Authenticate as Admin using access code or configured email/password."""
    # Check access code first if provided
    if login_request.code and verify_admin_code(login_request.code):
        token, expires_in = create_admin_token()
        logger.info("Admin code login successful via /admin/login")
        return AdminLoginResponse(
            access_token=token,
            role="admin",
            username=config.ADMIN_USERNAME,
            expires_in=expires_in,
        )

    # Fallback to email and password
    if login_request.email and login_request.password and verify_admin_credentials(login_request.email, login_request.password):
        token, expires_in = create_admin_token()
        logger.info("Admin login successful via email/password")
        return AdminLoginResponse(
            access_token=token,
            role="admin",
            username=config.ADMIN_USERNAME,
            expires_in=expires_in,
        )

    logger.warning("Failed admin login attempt")
    return create_error_response(
        "INVALID_CREDENTIALS",
        "Invalid admin access code or credentials",
        status.HTTP_401_UNAUTHORIZED,
    )


@app.get("/admin/verify")
async def admin_verify(request: Request):
    """Verify that current admin token is active."""
    require_admin(request)
    return {"status": "ok", "role": "admin", "username": config.ADMIN_USERNAME}


# ============================================================================
# Promo Code & Access Verification Endpoints
# ============================================================================

@app.post("/promo/verify", response_model=PromoVerifyResponse)
async def verify_promo_code_endpoint(payload: PromoVerifyRequest):
    """Verify and redeem access code from the chat screen popup. Supports both Student codes and Admin Access Code."""
    code_raw = payload.code

    # 1. Check if it is the Admin Access Code (e.g. ADMIN-TM-NEW, ignoring spaces)
    if verify_admin_code(code_raw):
        admin_token, _ = create_admin_token()
        promo_token = create_signed_promo_token("ADMIN")
        logger.info("Admin access code successfully verified on /promo/verify")
        return PromoVerifyResponse(
            valid=True,
            promo_token=promo_token,
            admin_token=admin_token,
            is_admin=True,
            code="ADMIN-TM-NEW",
            label="Administrator Access",
            message="Admin access code verified! Full access granted.",
        )

    # 2. Check standard student access code
    result = verify_and_redeem_promo_code(code_raw)
    if not result.get("valid"):
        msg = result.get("message", "Invalid access code. Please check and try again.")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "valid": False,
                "message": msg,
                "error": {
                    "code": "INVALID_CODE",
                    "message": msg,
                },
            },
        )
    return PromoVerifyResponse(
        valid=True,
        promo_token=result.get("promo_token"),
        code=result.get("code"),
        label=result.get("label"),
        message=result.get("message", "Access code verified successfully"),
    )


@app.get("/promo/check", response_model=PromoTokenCheckResponse)
async def check_promo_token_endpoint(request: Request):
    """Check if existing promo token in localStorage is still valid."""
    promo_token = request.headers.get("X-Promo-Token")
    if not promo_token:
        auth_header = request.headers.get("Authorization")
        if auth_header:
            try:
                promo_token = extract_token_from_header(auth_header)
            except Exception:
                pass

    if not promo_token:
        return PromoTokenCheckResponse(valid=False)

    code = verify_signed_promo_token(promo_token)
    if code:
        if code == "ADMIN" or code.startswith("ADMIN"):
            return PromoTokenCheckResponse(valid=True, code="ADMIN-TM-NEW", label="Administrator Access")
        record = get_promo_code_by_code(code)
        label = record.get("label") if record else None
        return PromoTokenCheckResponse(valid=True, code=code, label=label)
    return PromoTokenCheckResponse(valid=False)


@app.get("/admin/promo-codes", response_model=AdminPromoListResponse)
async def admin_get_promo_codes(request: Request):
    """Admin endpoint to list all promo codes and statistics."""
    require_admin(request)
    codes = list_promo_codes()
    stats = get_promo_stats()
    return AdminPromoListResponse(
        codes=[PromoCodeItemResponse(**c) for c in codes],
        stats=stats
    )


@app.post("/admin/promo-codes", response_model=PromoCodeItemResponse)
async def admin_create_promo_code(payload: AdminPromoCreateRequest, request: Request):
    """Admin endpoint to create or generate a promo code."""
    require_admin(request)
    try:
        new_code = create_promo_code(
            code=payload.code,
            prefix=payload.prefix,
            label=payload.label,
            max_uses=payload.max_uses,
            created_by=config.ADMIN_USERNAME or "admin",
        )
        return PromoCodeItemResponse(**new_code)
    except ValueError as e:
        return create_error_response("PROMO_EXISTS", str(e), status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Failed to create promo code: %s", e)
        return create_error_response("PROMO_CREATE_FAILED", str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.patch("/admin/promo-codes/{code_id}/toggle", response_model=PromoCodeItemResponse)
async def admin_toggle_promo_code(code_id: str, request: Request):
    """Admin endpoint to enable/disable a promo code."""
    require_admin(request)
    updated = toggle_promo_code_status(code_id)
    if not updated:
        return create_error_response("PROMO_NOT_FOUND", "Promo code not found", status.HTTP_404_NOT_FOUND)
    return PromoCodeItemResponse(**updated)


@app.delete("/admin/promo-codes/{code_id}")
async def admin_delete_promo_code(code_id: str, request: Request):
    """Admin endpoint to delete a promo code."""
    require_admin(request)
    success = delete_promo_code(code_id)
    if not success:
        return create_error_response("PROMO_NOT_FOUND", "Promo code not found", status.HTTP_404_NOT_FOUND)
    return {"status": "deleted", "code_id": code_id}


@app.get("/admin/documents", response_model=list[KnowledgeDocumentResponse])
async def get_admin_documents(request: Request):
    """List every distinct PDF currently indexed in the knowledge base with its lesson association."""
    require_admin(request)
    docs = list_documents()
    lessons = list_lessons()

    doc_to_lesson: dict[str, tuple[str, str]] = {}
    for lesson in lessons:
        norm = _normalise_lesson(lesson)
        for doc in norm.get("documents", []):
            if doc.get("document_id"):
                doc_to_lesson[str(doc["document_id"])] = (str(norm["id"]), norm.get("title", ""))
        if norm.get("document_id"):
            doc_to_lesson[str(norm["document_id"])] = (str(norm["id"]), norm.get("title", ""))

    enriched = []
    for doc in docs:
        doc_dict = dict(doc)
        lid, ltitle = doc_to_lesson.get(str(doc.get("document_id")), (None, None))
        doc_dict["lesson_id"] = lid
        doc_dict["lesson_title"] = ltitle
        enriched.append(KnowledgeDocumentResponse(**doc_dict))
    return enriched


@app.delete("/admin/documents/{document_id}")
async def admin_delete_document(
    document_id: str,
    request: Request,
    workspace_id: Optional[str] = None,
):
    """
    Permanently delete a PDF and all its chunks from the database/vector store
    and detach it from any lessons in the database.
    """
    require_admin(request)
    try:
        deleted_count = delete_document(workspace_id=workspace_id, document_id=document_id)
        affected_lessons = detach_document_from_all_lessons(document_id)
        logger.info(
            "Admin permanently deleted document %s (%d chunks deleted, detached from %d lessons)",
            document_id,
            deleted_count,
            len(affected_lessons),
        )
        return {
            "status": "deleted",
            "document_id": document_id,
            "chunks_deleted": deleted_count,
            "affected_lessons": affected_lessons,
        }
    except Exception as e:
        logger.exception("Failed to delete document %s: %s", document_id, e)
        return create_error_response("DELETE_FAILED", str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.post("/admin/lessons/{lesson_id}/assign-document/{document_id}", response_model=LessonResponse)
async def admin_assign_document_to_lesson(
    lesson_id: str,
    document_id: str,
    request: Request,
):
    """Assign an existing knowledge base PDF to a lesson without re-uploading."""
    require_admin(request)
    lesson = get_lesson(lesson_id)
    if not lesson:
        return create_error_response("LESSON_NOT_FOUND", "Lesson not found", status.HTTP_404_NOT_FOUND)

    all_docs = list_documents()
    target_doc = next((d for d in all_docs if str(d.get("document_id")) == str(document_id)), None)
    if not target_doc:
        return create_error_response("DOCUMENT_NOT_FOUND", "Document not found in knowledge base", status.HTTP_404_NOT_FOUND)

    updated = attach_document_to_lesson(
        lesson_id=lesson_id,
        document_id=document_id,
        pdf_name=target_doc.get("pdf_name", "document.pdf"),
        pages_count=target_doc.get("pages_count", 0),
        chunks_count=target_doc.get("chunks_count", 0),
    )
    if not updated:
        return create_error_response("ASSIGN_FAILED", "Failed to assign document to lesson", status.HTTP_500_INTERNAL_SERVER_ERROR)
    return lesson_response(updated)


# ============================================================================
# Lessons Management Endpoints (Public List, Admin Mutations)
# ============================================================================

@app.get("/lessons", response_model=list[LessonResponse])
async def get_lessons():
    """Get list of all available lessons."""
    lessons = list_lessons()
    return [lesson_response(lesson) for lesson in lessons]


@app.post("/lessons", response_model=LessonResponse)
async def create_new_lesson(request: Request, body: LessonCreateRequest):
    """Create a new lesson. Requires Admin authentication."""
    require_admin(request)
    new_lesson = create_lesson(title=body.title, description=body.description)
    logger.info("Admin created lesson: %s (%s)", new_lesson["title"], new_lesson["id"])
    return lesson_response(new_lesson)


@app.post("/lessons/{lesson_id}/upload", response_model=LessonResponse)
async def upload_lesson_pdf(
    lesson_id: str,
    request: Request,
    file: UploadFile = File(...),
):
    """Upload a PDF for a specific lesson and build its vector knowledge base."""
    require_admin(request)

    lesson = get_lesson(lesson_id)
    if not lesson:
        return create_error_response("LESSON_NOT_FOUND", "Lesson not found", status.HTTP_404_NOT_FOUND)

    if not file.filename:
        return create_error_response("NO_FILENAME", "Uploaded file must have a filename", status.HTTP_400_BAD_REQUEST)

    try:
        result = process_pdf(file.file, file.filename)
        document_id = result["document_id"]
        workspace_id = lesson.get("workspace_id", SHARED_WORKSPACE_ID)

        chunks_count = store_chunks(
            chunks=result["chunks"],
            workspace_id=workspace_id,
            document_id=document_id,
        )

        updated = attach_document_to_lesson(
            lesson_id=lesson_id,
            document_id=document_id,
            pdf_name=result["pdf_name"],
            pages_count=result["pages_processed"],
            chunks_count=chunks_count,
        )

        return lesson_response(updated)

    except PDFValidationError as e:
        return create_error_response(e.code, e.message, status.HTTP_400_BAD_REQUEST)
    except PDFEmptyError as e:
        return create_error_response(e.code, e.message, status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Unexpected error uploading PDF for lesson")
        return create_error_response("UPLOAD_FAILED", str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.delete("/lessons/{lesson_id}/documents/{document_id}")
async def delete_lesson_document(lesson_id: str, document_id: str, request: Request):
    """Remove one PDF and its indexed chunks without deleting the lesson."""
    require_admin(request)
    lesson = get_lesson(lesson_id)
    if not lesson:
        return create_error_response("LESSON_NOT_FOUND", "Lesson not found", status.HTTP_404_NOT_FOUND)

    lesson_document_ids = {
        str(item.get("document_id"))
        for item in lesson.get("documents", [])
        if item.get("document_id")
    }
    if lesson.get("document_id"):
        lesson_document_ids.add(str(lesson["document_id"]))
    if str(document_id) not in lesson_document_ids:
        return create_error_response(
            "LESSON_DOCUMENT_NOT_FOUND",
            "PDF is not attached to this lesson",
            status.HTTP_404_NOT_FOUND,
        )

    try:
        delete_document(
            workspace_id=lesson.get("workspace_id", SHARED_WORKSPACE_ID),
            document_id=document_id,
        )
    except VectorStoreOperationError as error:
        return create_error_response(error.code, error.message, status.HTTP_500_INTERNAL_SERVER_ERROR)

    updated = remove_document_from_lesson(lesson_id, document_id)
    if not updated:
        return create_error_response(
            "LESSON_DOCUMENT_NOT_FOUND",
            "The PDF association changed while it was being removed",
            status.HTTP_409_CONFLICT,
        )
    return lesson_response(updated)


@app.delete("/lessons/{lesson_id}")
async def delete_lesson_endpoint(lesson_id: str, request: Request):
    """Delete a lesson and its knowledge base chunks."""
    require_admin(request)
    success = delete_lesson(lesson_id)
    if not success:
        return create_error_response("LESSON_NOT_FOUND", "Lesson not found", status.HTTP_404_NOT_FOUND)
    return {"status": "deleted", "lesson_id": lesson_id}


@app.post("/admin/upload", response_model=UploadResponse)
async def admin_direct_upload(
    request: Request,
    file: UploadFile = File(...),
):
    """
    Directly upload a PDF to the general knowledge base without a lesson.
    Requires Admin authentication.
    """
    require_admin(request)
    if not file.filename:
        return create_error_response("NO_FILENAME", "Uploaded file must have a filename", status.HTTP_400_BAD_REQUEST)

    try:
        result = process_pdf(file.file, file.filename)
        document_id = result["document_id"]
        stored = store_chunks(
            chunks=result["chunks"],
            workspace_id=SHARED_WORKSPACE_ID,
            document_id=document_id,
        )
        logger.info("Admin directly uploaded PDF %s (%d chunks)", file.filename, stored)
        return UploadResponse(
            document_id=document_id,
            pdf_name=result["pdf_name"],
            pages_processed=result["pages_processed"],
            chunks_created=stored,
            status="processed"
        )
    except PDFValidationError as e:
        return create_error_response(e.code, e.message, status.HTTP_400_BAD_REQUEST)
    except PDFEmptyError as e:
        return create_error_response(e.code, e.message, status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Unexpected error in admin direct upload")
        return create_error_response("UPLOAD_FAILED", str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# General Upload, Search, Delete Endpoints
# ============================================================================

@app.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
):
    """Upload and process a PDF file into workspace knowledge base."""
    workspace_id = get_workspace_id_from_request(request)

    if not file.filename:
        return create_error_response("NO_FILENAME", "Uploaded file must have a filename", status.HTTP_400_BAD_REQUEST)

    try:
        result = process_pdf(file.file, file.filename)
        stored = store_chunks(
            chunks=result["chunks"],
            workspace_id=workspace_id,
            document_id=result["document_id"],
        )

        return UploadResponse(
            document_id=result["document_id"],
            pdf_name=result["pdf_name"],
            pages_processed=result["pages_processed"],
            chunks_created=stored,
            status=result["status"],
        )

    except PDFValidationError as e:
        return create_error_response(e.code, e.message, status.HTTP_400_BAD_REQUEST)
    except PDFEmptyError as e:
        return create_error_response(e.code, e.message, status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Unexpected error during PDF upload")
        return create_error_response("UPLOAD_FAILED", "An unexpected error occurred", status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.post("/search", response_model=SearchResponse)
async def search_chunks(
    request: Request,
    search_request: SearchRequest,
):
    """Search for similar chunks in a document using vector similarity."""
    workspace_id = get_workspace_id_from_request(request)

    try:
        results = search_similar_chunks(
            query=search_request.query,
            workspace_id=workspace_id,
            document_id=search_request.document_id,
            top_k=search_request.top_k,
        )

        search_results = [
            SearchResult(
                id=r["id"],
                document_id=r["document_id"],
                pdf_name=r["pdf_name"],
                content=r["content"],
                metadata=r["metadata"],
                page_number=r["page_number"],
                chunk_index=r["chunk_index"],
                similarity=r["similarity"],
            )
            for r in results
        ]

        return SearchResponse(
            results=search_results,
            query=search_request.query,
            document_id=search_request.document_id,
            count=len(search_results),
        )

    except Exception as e:
        logger.exception("Unexpected error during search")
        return create_error_response("SEARCH_FAILED", str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.delete("/documents/{document_id}", response_model=DeleteResponse)
async def delete_document_endpoint(
    request: Request,
    document_id: str,
):
    """Delete all chunks for a document."""
    workspace_id = get_workspace_id_from_request(request)

    try:
        deleted_count = delete_document(workspace_id, document_id)
        return DeleteResponse(
            document_id=document_id,
            chunks_deleted=deleted_count,
            status="deleted" if deleted_count > 0 else "not_found"
        )
    except Exception as e:
        logger.exception("Unexpected error during document deletion")
        return create_error_response("DELETE_FAILED", str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# Phase 3: Ask Endpoint (Supports Lesson ID, Document ID, or Knowledge Base)
# ============================================================================

@app.post("/ask", response_model=AskResponse)
async def ask_question(
    request: Request,
    ask_request: AskRequest,
):
    """
    Ask a question about a PDF document, a selected Lesson, or knowledge base.
    Uses the Intelligent Knowledge-Based Reasoning Engine to synthesize
    syllabus content with analytical and practical examination reasoning.
    """
    # Enforce promo code / admin access security
    require_promo_or_admin_access(request)

    try:
        image_data_urls = validate_image_data_urls(ask_request.images)
    except ValueError as error:
        return create_error_response("INVALID_IMAGE", str(error), status.HTTP_400_BAD_REQUEST)

    target_workspace_id = SHARED_WORKSPACE_ID
    target_document_id = None
    target_document_ids = list(ask_request.document_ids) if ask_request.document_ids else []

    # Case 1: Specific Lesson ID provided
    if ask_request.lesson_id:
        lesson = get_lesson(ask_request.lesson_id)
        if not lesson:
            return create_error_response("LESSON_NOT_FOUND", "Selected lesson not found", status.HTTP_404_NOT_FOUND)
        lesson_documents = lesson.get("documents", [])
        target_document_ids = [
            str(item["document_id"])
            for item in lesson_documents
            if item.get("document_id")
        ]
        if not target_document_ids and lesson.get("document_id"):
            target_document_ids = [str(lesson["document_id"])]
        if not target_document_ids:
            return AskResponse(
                answer="This lesson does not have a PDF uploaded yet. Please ask the instructor/admin to upload lecture material.",
                sources=[],
                question_type="explanation",
                reasoning_status="abstain_unrelated",
                knowledge_coverage="unrelated",
                additional_knowledge_used=False,
                abstained=True,
                thinking="Selected lesson has no attached document yet.",
            )
        target_workspace_id = lesson.get("workspace_id", SHARED_WORKSPACE_ID)

    # Case 2: Document ID or Document IDs provided directly
    elif ask_request.document_id or ask_request.document_ids:
        if ask_request.document_id:
            target_document_id = ask_request.document_id
        auth_header = request.headers.get("Authorization")
        if auth_header:
            try:
                token = extract_token_from_header(auth_header)
                target_workspace_id = verify_workspace_token(token)
            except Exception:
                target_workspace_id = SHARED_WORKSPACE_ID

    # Case 3: Asked directly without selecting a lesson or document
    else:
        lessons = list_lessons()
        ready_lessons = [l for l in lessons if l.get("documents") or l.get("document_id")]
        if ready_lessons and len(ready_lessons) == 1:
            target_document_ids = [
                str(item["document_id"])
                for item in ready_lessons[0].get("documents", [])
                if item.get("document_id")
            ]
            if not target_document_ids and ready_lessons[0].get("document_id"):
                target_document_ids = [str(ready_lessons[0]["document_id"])]
        else:
            target_document_id = None
        target_workspace_id = SHARED_WORKSPACE_ID

    top_k = ask_request.top_k or config.TOP_K
    min_similarity = ask_request.min_similarity if ask_request.min_similarity is not None else config.MIN_SIMILARITY

    try:
        response: RAGResponse = generate_answer(
            question=ask_request.question,
            workspace_id=target_workspace_id,
            document_id=target_document_id,
            document_ids=target_document_ids if target_document_ids else None,
            marks=ask_request.marks,
            answer_style=ask_request.answer_style or "exam",
            top_k=top_k,
            min_similarity=min_similarity,
            image_data_urls=image_data_urls,
        )

        qa_model = (
            QuestionAnalysisModel(**response.question_analysis)
            if response.question_analysis
            else None
        )
        ts_model = (
            ThinkingSummaryModel(**response.thinking_summary)
            if response.thinking_summary
            else None
        )

        # Map documents to lesson titles
        doc_to_lesson_title = {}
        for l in list_lessons():
            ltitle = l.get("title")
            for doc in l.get("documents", []):
                if doc.get("document_id"):
                    doc_to_lesson_title[str(doc["document_id"])] = ltitle
                if doc.get("pdf_name"):
                    doc_to_lesson_title[str(doc["pdf_name"])] = ltitle
            if l.get("document_id"):
                doc_to_lesson_title[str(l["document_id"])] = ltitle
            if l.get("pdf_name"):
                doc_to_lesson_title[str(l["pdf_name"])] = ltitle

        requested_lesson_title = None
        if ask_request.lesson_id:
            req_l = get_lesson(ask_request.lesson_id)
            if req_l:
                requested_lesson_title = req_l.get("title")

        sources = []
        for s in response.sources:
            raw_doc_name = s.get("document_name") or s.get("pdf_name") or "document.pdf"
            clean_name = re.sub(r'\.pdf$', '', raw_doc_name, flags=re.IGNORECASE).strip()
            l_name = (
                s.get("lesson_name")
                or requested_lesson_title
                or doc_to_lesson_title.get(str(s.get("chunk_id", "")))
                or doc_to_lesson_title.get(raw_doc_name)
                or clean_name
            )
            sources.append(
                SourceInfo(
                    document_name=raw_doc_name,
                    page_number=s.get("page_number", 1),
                    chunk_index=s.get("chunk_index", 0),
                    excerpt=s.get("excerpt", ""),
                    support_type=s.get("support_type", "direct"),
                    chunk_id=s.get("chunk_id"),
                    pdf_name=s.get("pdf_name") or raw_doc_name,
                    similarity=s.get("similarity"),
                    cited=s.get("cited", True),
                    lesson_name=l_name,
                )
            )

        logger.info(
            "Ask completed: question='%s', type=%s, coverage=%s, status=%s, sources=%d",
            ask_request.question[:50],
            response.question_type,
            response.knowledge_coverage,
            response.reasoning_status,
            len(sources),
        )

        return AskResponse(
            answer=response.answer,
            question_analysis=qa_model,
            thinking_summary=ts_model,
            sources=sources,
            answer_status=response.answer_status,
            knowledge_coverage=response.knowledge_coverage,
            question_type=response.question_type,
            reasoning_status=response.reasoning_status,
            additional_knowledge_used=response.additional_knowledge_used,
            abstained=response.abstained,
            thinking=response.thinking or "",
        )

    except CitationValidationError as e:
        logger.warning("Citation validation failed: %s", e)
        return AskResponse(
            answer="This question cannot be verified from the uploaded materials.",
            sources=[],
            question_type="explanation",
            reasoning_status="abstain_uncertain",
            knowledge_coverage="insufficient",
            additional_knowledge_used=False,
            abstained=True,
            thinking="Citation validation failed.",
        )

    except LLMError as e:
        logger.error("LLM error: %s", e)
        message = str(e)
        if image_data_urls and "vision-capable" in message.lower():
            return create_error_response(
                "IMAGE_ANALYSIS_UNAVAILABLE",
                message.split("Provider detail:")[0].strip(),
                status.HTTP_502_BAD_GATEWAY,
            )
        return create_error_response("LLM_ERROR", "Failed to generate answer. Please try again.", status.HTTP_502_BAD_GATEWAY)

    except RAGError as e:
        logger.error("RAG error: %s", e)
        return create_error_response("RAG_ERROR", str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        logger.exception("Unexpected error during ask")
        return create_error_response(
            "ASK_FAILED",
            "An unexpected error occurred while processing the question",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@app.post("/ask/stream")
async def ask_question_stream(
    request: Request,
    ask_request: AskRequest,
):
    """
    Stream live progress events (milestones 1 through 7) and final verified answer.
    Emits real-time SSE progress events as each pipeline stage completes.
    """
    # Enforce promo code / admin access security
    require_promo_or_admin_access(request)

    target_workspace_id = SHARED_WORKSPACE_ID
    target_document_id = None
    target_document_ids = list(ask_request.document_ids) if ask_request.document_ids else []

    if ask_request.lesson_id:
        lesson = get_lesson(ask_request.lesson_id)
        if not lesson:
            return create_error_response("LESSON_NOT_FOUND", "Selected lesson not found", status.HTTP_404_NOT_FOUND)
        lesson_documents = lesson.get("documents", [])
        target_document_ids = [
            str(item["document_id"])
            for item in lesson_documents
            if item.get("document_id")
        ]
        if not target_document_ids and lesson.get("document_id"):
            target_document_ids = [str(lesson["document_id"])]
        target_workspace_id = lesson.get("workspace_id", SHARED_WORKSPACE_ID)
    elif ask_request.document_id or ask_request.document_ids:
        if ask_request.document_id:
            target_document_id = ask_request.document_id
        auth_header = request.headers.get("Authorization")
        if auth_header:
            try:
                token = extract_token_from_header(auth_header)
                target_workspace_id = verify_workspace_token(token)
            except Exception:
                target_workspace_id = SHARED_WORKSPACE_ID
    else:
        lessons = list_lessons()
        ready_lessons = [l for l in lessons if l.get("document_id")]
        if ready_lessons and len(ready_lessons) == 1:
            target_document_id = ready_lessons[0]["document_id"]
        else:
            target_document_id = None
        target_workspace_id = SHARED_WORKSPACE_ID

    top_k = ask_request.top_k or config.TOP_K
    min_similarity = ask_request.min_similarity if ask_request.min_similarity is not None else config.MIN_SIMILARITY

    def event_stream():
        try:
            for event in generate_answer_stream(
                question=ask_request.question,
                workspace_id=target_workspace_id,
                document_id=target_document_id,
                document_ids=target_document_ids if target_document_ids else None,
                marks=ask_request.marks,
                answer_style=ask_request.answer_style or "exam",
                top_k=top_k,
                min_similarity=min_similarity,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.exception("Error in answer stream")
            yield f"data: {json.dumps({'stage': -1, 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Exam Helper Bot API",
        "docs": "/docs",
        "health": "/health",
        "gradio": "/gradio",
    }


# -------------------------------------------------------------
# Hugging Face Gradio Runner (Mounts FastAPI onto Gradio)
# -------------------------------------------------------------
import gradio as gr

with gr.Blocks(title="Exam Helper Bot API") as demo:
    gr.Markdown("# 🤖 Exam Helper Bot Backend API")
    gr.Markdown("FastAPI backend is active and running on Hugging Face Spaces.")
    gr.Markdown("Endpoints are available for the Vercel frontend:")
    gr.Markdown("- **Health check**: `/health`")
    gr.Markdown("- **Interactive API Docs**: `/docs`")
    gr.Markdown("### ZeroGPU embedding check")
    gr.Markdown("This event uses the same GPU-decorated embedding function as PDF indexing and search.")
    embedding_input = gr.JSON(
        value=["ZeroGPU embedding check"],
        label="Text array",
    )
    embedding_output = gr.JSON(label="Embeddings")
    gr.Button("Generate embeddings").click(
        fn=generate_embeddings_on_zero_gpu,
        inputs=embedding_input,
        outputs=embedding_output,
    )

app = gr.mount_gradio_app(app, demo, path="/gradio", ssr_mode=False)

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
