/** Frontend API client for PDF RAG Assistant backend */

import type {
  SessionResponse,
  UploadResponse,
  AskRequest,
  AskResponse,
  SearchRequest,
  SearchResponse,
  DeleteResponse,
  ErrorResponse,
  SourceInfo,
  Lesson,
  AdminLoginResponse,
  AdminVerificationResponse,
  KnowledgeDocument,
  LessonDocument,
  PromoVerifyResponse,
  PromoTokenCheckResponse,
  PromoCodeItem,
  PromoStats,
  AdminPromoListResponse,
  AdminPromoCreateRequest,
} from "./types";

export type {
  SessionResponse,
  UploadResponse,
  AskRequest,
  AskResponse,
  SearchRequest,
  SearchResponse,
  DeleteResponse,
  ErrorResponse,
  SourceInfo,
  Lesson,
  LessonDocument,
  AdminLoginResponse,
  AdminVerificationResponse,
  KnowledgeDocument,
  PromoVerifyResponse,
  PromoTokenCheckResponse,
  PromoCodeItem,
  PromoStats,
  AdminPromoListResponse,
  AdminPromoCreateRequest,
};

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001").replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") || "";

  if (!response.ok) {
    let errorMessage = `Request failed with status ${response.status}`;
    let errorCode = "HTTP_ERROR";

    try {
      if (contentType.includes("application/json")) {
        const errorData = await response.json();
        const errObj = errorData as ErrorResponse & { message?: string; detail?: string };
        errorMessage =
          errObj.error?.message ||
          errObj.message ||
          errObj.detail ||
          (typeof errorData === "string" ? errorData : errorMessage);
        errorCode = errObj.error?.code || errorCode;
      } else {
        const text = await response.text();
        if (text) {
          errorMessage = text.length > 200 ? `${text.slice(0, 200)}...` : text;
        }
      }
    } catch {
      // Fallback to default status message
    }

    throw new ApiError(response.status, errorCode, errorMessage);
  }

  // Response is OK (2xx) - verify it is JSON
  if (!contentType.includes("application/json")) {
    throw new ApiError(
      response.status,
      "INVALID_RESPONSE",
      `Expected JSON response from backend but received '${contentType || "non-json"}'. Verify that NEXT_PUBLIC_API_URL points to the FastAPI backend.`
    );
  }

  try {
    const data = await response.json();
    return data as T;
  } catch {
    throw new ApiError(
      response.status,
      "JSON_PARSE_ERROR",
      "Failed to parse backend response as JSON."
    );
  }
}

function getAuthHeaders(token: string): HeadersInit {
  return {
    "Authorization": `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

export const api = {
  /** Create a new workspace session */
  async createSession(): Promise<SessionResponse> {
    const response = await fetch(`${API_BASE_URL}/session`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });
    return handleResponse<SessionResponse>(response);
  },

  /** Upload a PDF file */
  async uploadPdf(token: string, file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${API_BASE_URL}/upload`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
      },
      body: formData,
    });
    return handleResponse<UploadResponse>(response);
  },

  /** Search for similar chunks */
  async searchChunks(token: string, request: SearchRequest): Promise<SearchResponse> {
    const response = await fetch(`${API_BASE_URL}/search`, {
      method: "POST",
      headers: getAuthHeaders(token),
      body: JSON.stringify(request),
    });
    return handleResponse<SearchResponse>(response);
  },

  /** Ask a question about a PDF or Lesson */
  async askQuestion(
    token: string | null,
    request: AskRequest,
    promoToken?: string | null
  ): Promise<AskResponse> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const effectivePromoToken =
      promoToken ||
      (typeof window !== "undefined" ? localStorage.getItem("rag_promo_token") : null);
    const effectivePromoCode =
      typeof window !== "undefined" ? localStorage.getItem("rag_promo_code") : null;

    if (effectivePromoToken) {
      headers["X-Promo-Token"] = effectivePromoToken;
    }
    if (effectivePromoCode) {
      headers["X-Promo-Code"] = effectivePromoCode;
    }

    const response = await fetch(`${API_BASE_URL}/ask`, {
      method: "POST",
      headers,
      body: JSON.stringify(request),
    });
    return handleResponse<AskResponse>(response);
  },

  /** Ask a question with real-time live milestone progress streaming */
  async askQuestionStream(
    token: string | null,
    request: AskRequest,
    onProgress?: (milestone: { stage: number; status: string; progress?: number; result?: AskResponse }) => void,
    promoToken?: string | null
  ): Promise<AskResponse> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const effectivePromoToken =
      promoToken ||
      (typeof window !== "undefined" ? localStorage.getItem("rag_promo_token") : null);
    const effectivePromoCode =
      typeof window !== "undefined" ? localStorage.getItem("rag_promo_code") : null;

    if (effectivePromoToken) {
      headers["X-Promo-Token"] = effectivePromoToken;
    }
    if (effectivePromoCode) {
      headers["X-Promo-Code"] = effectivePromoCode;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/ask/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify(request),
      });

      if (!response.ok || !response.body) {
        return this.askQuestion(token, request, effectivePromoToken);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let finalResult: AskResponse | null = null;
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const block of lines) {
          const trimmed = block.trim();
          if (trimmed.startsWith("data: ")) {
            try {
              const data = JSON.parse(trimmed.slice(6));
              if (data.status) {
                onProgress?.(data);
              }
              if (data.result) {
                finalResult = data.result as AskResponse;
              }
            } catch {
              // Ignore partial parse
            }
          }
        }
      }

      if (finalResult) {
        return finalResult;
      }
      return this.askQuestion(token, request, effectivePromoToken);
    } catch {
      return this.askQuestion(token, request, effectivePromoToken);
    }
  },

  /** Delete a document */
  async deleteDocument(token: string, documentId: string): Promise<DeleteResponse> {
    const response = await fetch(`${API_BASE_URL}/documents/${documentId}`, {
      method: "DELETE",
      headers: {
        "Authorization": `Bearer ${token}`,
      },
    });
    return handleResponse<DeleteResponse>(response);
  },

  /** Check API health */
  async healthCheck(): Promise<{ status: string; port?: number }> {
    const response = await fetch(`${API_BASE_URL}/health`);
    return handleResponse<{ status: string; port?: number }>(response);
  },

  // ==========================================
  // Admin & Lesson APIs
  // ==========================================

  /** Authenticate as Admin using secret Admin Access Code */
  async adminLoginWithCode(code: string): Promise<AdminLoginResponse> {
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}/admin/login-code`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ code }),
      });
    } catch (error) {
      if (error instanceof TypeError) {
        throw new ApiError(
          0,
          "BACKEND_UNAVAILABLE",
          `Could not connect to the backend at ${API_BASE_URL}. Start the backend server and try again.`
        );
      }
      throw error;
    }
    return handleResponse<AdminLoginResponse>(response);
  },

  /** Authenticate as Admin */
  async adminLogin(email: string, password: string): Promise<AdminLoginResponse> {
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}/admin/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, password }),
      });
    } catch (error) {
      if (error instanceof TypeError) {
        throw new ApiError(
          0,
          "BACKEND_UNAVAILABLE",
          `Could not connect to the backend at ${API_BASE_URL}. Start the backend server and try again.`
        );
      }
      throw error;
    }
    return handleResponse<AdminLoginResponse>(response);
  },

  /** Verify admin token */
  async adminVerify(token: string): Promise<AdminVerificationResponse | null> {
    const response = await fetch(`${API_BASE_URL}/admin/verify`, {
        headers: {
          "Authorization": `Bearer ${token}`,
        },
      });
      if (!response.ok) return null;
      return handleResponse<AdminVerificationResponse>(response);
  },

  /** Get all available lessons */
  async getLessons(): Promise<Lesson[]> {
    const response = await fetch(`${API_BASE_URL}/lessons`);
    const data = await handleResponse<Lesson[]>(response);
    return Array.isArray(data) ? data : [];
  },

  /** Get all indexed PDFs for the admin inventory */
  async getAdminDocuments(token: string): Promise<KnowledgeDocument[]> {
    const response = await fetch(`${API_BASE_URL}/admin/documents`, {
      headers: { "Authorization": `Bearer ${token}` },
    });
    const data = await handleResponse<KnowledgeDocument[]>(response);
    return Array.isArray(data) ? data : [];
  },

  /** Create a new lesson (Admin only) */
  async createLesson(token: string, title: string, description?: string): Promise<Lesson> {
    const response = await fetch(`${API_BASE_URL}/lessons`, {
      method: "POST",
      headers: getAuthHeaders(token),
      body: JSON.stringify({ title, description }),
    });
    return handleResponse<Lesson>(response);
  },

  /** Upload a PDF for a lesson (Admin only) */
  async uploadLessonPdf(token: string, lessonId: string, file: File): Promise<Lesson> {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${API_BASE_URL}/lessons/${lessonId}/upload`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
      },
      body: formData,
    });
    return handleResponse<Lesson>(response);
  },

  /** Remove one PDF from a lesson without deleting the lesson */
  async removeLessonPdf(token: string, lessonId: string, documentId: string): Promise<Lesson> {
    const response = await fetch(
      `${API_BASE_URL}/lessons/${lessonId}/documents/${documentId}`,
      {
        method: "DELETE",
        headers: { "Authorization": `Bearer ${token}` },
      }
    );
    return handleResponse<Lesson>(response);
  },

  /** Delete a lesson (Admin only) */
  async deleteLesson(token: string, lessonId: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/lessons/${lessonId}`, {
      method: "DELETE",
      headers: {
        "Authorization": `Bearer ${token}`,
      },
    });
    await handleResponse<{ status: string }>(response);
  },

  /** Directly upload a PDF to knowledge base without a lesson (Admin only) */
  async adminDirectUpload(token: string, file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${API_BASE_URL}/admin/upload`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
      },
      body: formData,
    });
    return handleResponse<UploadResponse>(response);
  },

  /** Permanently delete an indexed PDF from knowledge base & lessons (Admin only) */
  async adminDeleteDocument(
    token: string,
    documentId: string,
    workspaceId?: string
  ): Promise<{ status: string; document_id: string; chunks_deleted: number }> {
    const url = new URL(`${API_BASE_URL}/admin/documents/${documentId}`);
    if (workspaceId) {
      url.searchParams.set("workspace_id", workspaceId);
    }
    const response = await fetch(url.toString(), {
      method: "DELETE",
      headers: {
        "Authorization": `Bearer ${token}`,
      },
    });
    return handleResponse<{ status: string; document_id: string; chunks_deleted: number }>(response);
  },

  /** Assign an existing knowledge base PDF to a lesson without re-uploading (Admin only) */
  async assignDocumentToLesson(
    token: string,
    lessonId: string,
    documentId: string
  ): Promise<Lesson> {
    const response = await fetch(
      `${API_BASE_URL}/admin/lessons/${lessonId}/assign-document/${documentId}`,
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
        },
      }
    );
    return handleResponse<Lesson>(response);
  },

  // ==========================================
  // Promo Code & Access Verification APIs
  // ==========================================

  /** Verify and redeem a promo code from the student chat screen */
  async verifyPromoCode(code: string): Promise<PromoVerifyResponse> {
    const response = await fetch(`${API_BASE_URL}/promo/verify`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ code }),
    });
    return handleResponse<PromoVerifyResponse>(response);
  },

  /** Check if saved promo token is still valid */
  async checkPromoToken(token?: string | null): Promise<PromoTokenCheckResponse> {
    const savedToken =
      token || (typeof window !== "undefined" ? localStorage.getItem("rag_promo_token") : null);
    if (!savedToken) {
      return { valid: false };
    }

    try {
      const response = await fetch(`${API_BASE_URL}/promo/check`, {
        method: "GET",
        headers: {
          "X-Promo-Token": savedToken,
        },
      });
      return handleResponse<PromoTokenCheckResponse>(response);
    } catch {
      return { valid: false };
    }
  },

  /** Get list of all promo codes & stats (Admin only) */
  async getAdminPromoCodes(adminToken: string): Promise<AdminPromoListResponse> {
    const response = await fetch(`${API_BASE_URL}/admin/promo-codes`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${adminToken}`,
      },
    });
    const data = await handleResponse<AdminPromoListResponse>(response);
    return {
      codes: Array.isArray(data?.codes) ? data.codes : [],
      stats: data?.stats || { total_codes: 0, active_codes: 0, total_redemptions: 0 },
    };
  },

  /** Create/generate a new promo code (Admin only) */
  async createAdminPromoCode(
    adminToken: string,
    payload: AdminPromoCreateRequest
  ): Promise<PromoCodeItem> {
    const response = await fetch(`${API_BASE_URL}/admin/promo-codes`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${adminToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    return handleResponse<PromoCodeItem>(response);
  },

  /** Toggle promo code active/inactive (Admin only) */
  async toggleAdminPromoCode(adminToken: string, codeId: string): Promise<PromoCodeItem> {
    const response = await fetch(`${API_BASE_URL}/admin/promo-codes/${codeId}/toggle`, {
      method: "PATCH",
      headers: {
        "Authorization": `Bearer ${adminToken}`,
      },
    });
    return handleResponse<PromoCodeItem>(response);
  },

  /** Delete a promo code (Admin only) */
  async deleteAdminPromoCode(
    adminToken: string,
    codeId: string
  ): Promise<{ status: string; code_id: string }> {
    const response = await fetch(`${API_BASE_URL}/admin/promo-codes/${codeId}`, {
      method: "DELETE",
      headers: {
        "Authorization": `Bearer ${adminToken}`,
      },
    });
    return handleResponse<{ status: string; code_id: string }>(response);
  },
};
