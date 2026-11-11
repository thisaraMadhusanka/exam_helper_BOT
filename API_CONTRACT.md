# PDF RAG Assistant — API Contract

**Base path:** `/`  
**Content type:** JSON except PDF upload (`multipart/form-data`)  
**Authentication:** Signed anonymous workspace bearer token for all workspace-specific endpoints.

---

## 1. Common rules

- `POST /session` creates an anonymous workspace and returns a signed bearer token.
- Frontend sends `Authorization: Bearer <workspace_token>` for upload, search, ask, list, and delete operations.
- Backend validates signature and expiry and derives the `workspace_id` from the token.
- Never accept a raw `workspace_id` from the frontend as proof of ownership.
- IDs are UUID strings.
- API must return useful error messages with stable error codes.

## 2. Endpoints

### `POST /admin/login`

Authenticates with `ADMIN_EMAIL` and `ADMIN_PASSWORD` configured in the backend environment. The configured `ADMIN_USERNAME` is returned for dashboard display; credentials are never stored in the database or exposed through client-side configuration.

Request:

```json
{
  "email": "admin@example.com",
  "password": "<admin-password>"
}
```

Response:

```json
{
  "access_token": "signed-admin-token",
  "role": "admin",
  "username": "admin",
  "expires_in": 86400
}
```

### `GET /admin/verify`

Requires the admin bearer token returned by `/admin/login`. Returns the configured username for the protected `/admin` dashboard.

### `GET /health`

Returns process health. It must not return secrets, environment values, provider keys, or database credentials.

Example:

```json
{"status":"ok"}
```

### `POST /session`

Creates an anonymous workspace token. The frontend may call this on first load and keep the token in `sessionStorage`.

Response:

```json
{
  "access_token": "signed-token-value",
  "token_type": "bearer",
  "expires_in": 604800
}
```

### `POST /upload`

Headers: `Authorization: Bearer ...`  
Body: multipart form field `file` (PDF)

Response:

```json
{
  "document_id": "uuid",
  "pdf_name": "lecture-notes.pdf",
  "pages_processed": 18,
  "chunks_created": 23,
  "status": "processed"
}
```

### `POST /search`

Headers: `Authorization: Bearer ...`  
Body:

```json
{
  "document_id": "uuid",
  "query": "What is the main idea?",
  "top_k": 4
}
```

Response:

```json
{
  "results": [
    {
      "chunk_id": "uuid",
      "content": "Text passage from the document...",
      "pdf_name": "lecture-notes.pdf",
      "page_number": 3,
      "chunk_index": 5,
      "similarity": 0.79,
      "metadata": {"page_number": 3, "chunk_index": 5}
    }
  ]
}
```

### `POST /ask`

Headers: `Authorization: Bearer ...`  
Body:

```json
{
  "document_id": "uuid",
  "question": "Explain the method described in the PDF.",
  "lesson_id": "optional-lesson-uuid",
  "images": ["data:image/png;base64,<base64-data>"]
}
```

`images` is optional and accepts up to three PNG, JPEG, or WebP data URLs, each under 5 MB. Image requests require the configured Groq or OpenRouter model to support vision; otherwise the API returns `IMAGE_ANALYSIS_UNAVAILABLE`. A lesson query uses every PDF associated with that lesson.

Response:

```json
{
  "answer": "The PDF describes ...",
  "abstained": false,
  "sources": [
    {
      "chunk_id": "uuid",
      "pdf_name": "lecture-notes.pdf",
      "page_number": 7,
      "chunk_index": 9,
      "content": "The retrieved evidence passage...",
      "similarity": 0.83
    }
  ]
}
```

For an unsupported question:

```json
{
  "answer": "I don't know, this is not in the PDF",
  "abstained": true,
  "sources": []
}
```

### Lesson and admin knowledge-base endpoints

- `GET /lessons` returns public lesson metadata. Each lesson includes a `documents` array with `document_id`, `pdf_name`, `pages_count`, and `chunks_count`.
- `GET /admin/documents` requires an admin bearer token and returns every distinct indexed PDF, including standalone uploads.
- `POST /lessons/{lesson_id}/upload` requires an admin bearer token and adds one PDF to the lesson without replacing its existing PDFs.
- `DELETE /lessons/{lesson_id}/documents/{document_id}` requires an admin bearer token and removes that PDF and its indexed chunks while keeping the lesson.

The Supabase `lessons.documents` JSONB column is added and backfilled by `database/schema.sql`; apply the schema update before deploying these endpoints to an existing project.

### `DELETE /documents/{document_id}`

Headers: `Authorization: Bearer ...`  
Deletes all chunks belonging to the document only when it belongs to the validated workspace.

Response:

```json
{"status":"deleted","document_id":"uuid"}
```

## 3. Common error response

```json
{
  "error": {
    "code": "UPSTREAM_PROVIDER_UNAVAILABLE",
    "message": "The AI service is temporarily unavailable. Please try again shortly."
  }
}
```

Do not return upstream stack traces, raw provider error bodies, prompt contents, environment variables, or credentials.
