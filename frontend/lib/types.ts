/** Frontend type definitions matching backend API contracts */

export interface SessionResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UploadResponse {
  document_id: string;
  pdf_name: string;
  pages_processed: number;
  chunks_created: number;
  status: string;
}

export interface SearchRequest {
  query: string;
  document_id?: string;
  top_k?: number;
}

export interface SearchResult {
  id: string;
  document_id: string;
  pdf_name: string;
  content: string;
  metadata: Record<string, unknown>;
  page_number: number;
  chunk_index: number;
  similarity: number;
}

export interface SearchResponse {
  results: SearchResult[];
  query: string;
  document_id?: string;
  count: number;
}

export interface AskRequest {
  question: string;
  document_ids?: string[];
  document_id?: string;
  lesson_id?: string;
  marks?: number;
  answer_style?: string;
  top_k?: number;
  min_similarity?: number;
  images?: string[];
}

export interface QuestionAnalysis {
  topic: string;
  subtopic: string;
  question_type: string;
  intent: string;
}

export interface ThinkingSummary {
  question_understanding: string;
  retrieval_summary: string;
  evidence_analysis: string;
  reasoning_summary: string;
  additional_knowledge_used: boolean;
}

export interface SourceInfo {
  document_name?: string;
  page_number: number;
  chunk_index: number;
  excerpt?: string;
  support_type?: string;
  chunk_id?: string;
  similarity?: number;
  pdf_name?: string;
  cited?: boolean;
  lesson_name?: string;
}

export interface AskResponse {
  answer: string;
  question_analysis?: QuestionAnalysis;
  thinking_summary?: ThinkingSummary;
  sources: SourceInfo[];
  answer_status?: string;
  knowledge_coverage?: string;
  question_type?: string;
  reasoning_status?: string;
  additional_knowledge_used?: boolean;
  abstained: boolean;
  thinking?: string;
}

export interface DeleteResponse {
  document_id: string;
  chunks_deleted: number;
  status: string;
}

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
  };
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  question_analysis?: QuestionAnalysis;
  thinking_summary?: ThinkingSummary;
  sources?: SourceInfo[];
  answer_status?: string;
  abstained?: boolean;
  thinking?: string;
  question_type?: string;
  knowledge_coverage?: string;
  additional_knowledge_used?: boolean;
  images?: string[];
  timestamp: Date;
}

export interface DocumentState {
  documentId: string | null;
  pdfName: string | null;
  pagesProcessed: number | null;
  chunksCreated: number | null;
  isUploading: boolean;
  uploadError: string | null;
}

export interface Lesson {
  id: string;
  title: string;
  description: string;
  workspace_id?: string;
  document_id?: string | null;
  pdf_name?: string | null;
  pages_count: number;
  chunks_count: number;
  documents?: LessonDocument[];
  created_at: string;
}

export interface LessonDocument {
  document_id: string;
  pdf_name: string;
  pages_count: number;
  chunks_count: number;
}

export interface KnowledgeDocument extends LessonDocument {
  workspace_id: string;
  created_at: string;
  lesson_id?: string | null;
  lesson_title?: string | null;
}

export interface ChatConversation {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: string;
  lessonId?: string | null;
}

export interface AdminLoginRequest {
  email: string;
  password: string;
}

export interface AdminLoginResponse {
  access_token: string;
  role: string;
  username: string;
  expires_in: number;
}

export interface AdminVerificationResponse {
  status: string;
  role: string;
  username: string;
}

export interface PromoVerifyResponse {
  valid: boolean;
  promo_token?: string;
  admin_token?: string;
  is_admin?: boolean;
  code?: string;
  label?: string;
  message: string;
}

export interface PromoTokenCheckResponse {
  valid: boolean;
  code?: string;
  label?: string;
}

export interface PromoCodeItem {
  id: string;
  code: string;
  label: string;
  max_uses?: number | null;
  used_count: number;
  is_active: boolean;
  created_at: string;
  created_by: string;
  last_used_at?: string | null;
}

export interface PromoStats {
  total_codes: number;
  active_codes: number;
  total_redemptions: number;
}

export interface AdminPromoListResponse {
  codes: PromoCodeItem[];
  stats: PromoStats;
}

export interface AdminPromoCreateRequest {
  code?: string;
  prefix?: string;
  length?: number;
  label?: string;
  max_uses?: number | null;
}
