# PDF RAG Assistant — Technology Stack & Hosting Decision

**Reviewed:** 8 November 2026  
**Decision status:** User-selected stack retained. Hosting alternatives are documented, not automatically adopted.

---

## 1. Stack summary

| Layer | Selected technology | Responsibility |
|---|---|---|
| Frontend | Next.js App Router, React, TypeScript | Student interface and client-side state |
| Styling | Tailwind CSS | Responsive UI and design system |
| Frontend hosting | Vercel Hobby | Deploy Next.js frontend |
| Backend language | Python 3.11+ | PDF, embedding, retrieval and RAG logic |
| Backend framework | FastAPI | REST API, validation and CORS |
| ASGI server | Uvicorn | Serve FastAPI REST endpoints in the Space |
| Container | Docker | Optional local CPU development container |
| Preferred backend host | Hugging Face Spaces — Gradio SDK, ZeroGPU | Host the REST API and mounted Gradio page; run embeddings through a registered `@spaces.GPU` event |
| Database | Supabase PostgreSQL | Persistent chunk and metadata storage |
| Vector extension | pgvector | Store 384-dimensional embeddings and perform cosine search |
| Embedding library | sentence-transformers | Create embeddings locally in the backend |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` | 384-dimensional sentence embeddings |
| PDF library | PyMuPDF (`fitz`) | Extract page text and page-level metadata |
| Primary LLM | Groq API — `openai/gpt-oss-120b` | Generate evidence-grounded answers |
| Fallback LLM | OpenRouter API — configurable free route/model | Secondary generation provider |
| API compatibility | OpenAI-compatible chat completions | Keep provider integration consistent |
| Python HTTP client | `httpx` / OpenAI SDK | API requests and timeouts |
| Database client | `supabase` Python SDK | Insert, delete and call vector RPC |
| Environment config | `python-dotenv` locally; host secrets in deployment | Configuration without hardcoded credentials |

## 2. Recommended implementation choices

### 2.1 Frontend

- Use the current stable Next.js release with the App Router and TypeScript.
- Keep the UI in `frontend/` and do not expose any server secret through a `NEXT_PUBLIC_` variable.
- Only `NEXT_PUBLIC_API_URL` is public. It contains the backend base URL, not a key.
- Use a small API helper in `frontend/lib/api.ts` so upload, search and ask calls share timeout and error handling.
- Store the anonymous workspace bearer token in `sessionStorage` for the MVP. Do not store provider API keys or Supabase credentials in the browser.
- Use native `FormData` for PDF uploads; do not manually set the multipart `Content-Type` header because the browser adds the boundary.

### 2.2 Backend

- Use FastAPI with Pydantic request/response models.
- Initialize the `SentenceTransformer` model once. In the ZeroGPU Space, load it on CUDA at module initialization and execute inference through a `@spaces.GPU` function registered as a Gradio event; use CPU locally.
- Use a ZeroGPU-supported PyTorch release (`torch>=2.8.0`) in Hugging Face requirements. Install CPU-only PyTorch separately for local Docker development.
- Keep the PDF processor independent of FastAPI so unit tests can call it directly.
- Run one process/worker initially to avoid loading duplicate copies of the embedding model into RAM.
- Let the Hugging Face Gradio SDK launch `app.py` on its assigned port. The optional local Dockerfile runs the same FastAPI app on port `7860`.

### 2.3 Embeddings and vector search

- Model: `sentence-transformers/all-MiniLM-L6-v2`.
- Expected dimensions: 384. The Supabase vector column must be `vector(384)`.
- The model card states that inputs longer than 256 word pieces are truncated. A 500-character chunk is the target, not a guarantee that every language/text type fits. Before embedding, check the model tokenizer length and split any chunk that exceeds the safe token budget while preserving page/chunk provenance and configured overlap. Do not silently embed truncated text.
- Keep the same embedding model and preprocessing configuration for both document chunks and question queries.
- Do not change the embedding model without re-embedding all stored chunks.
- Default `top_k=4` as requested; keep it configurable.
- Use cosine distance (`<=>`) in pgvector and return a similarity score such as `1 - cosine_distance`.
- A database RPC function must enforce both `workspace_id` and `document_id` filtering.

### 2.4 LLM providers

**Primary provider:** Groq, model ID exactly `openai/gpt-oss-120b`.

- Base URL: `https://api.groq.com/openai/v1`
- Use the OpenAI-compatible chat completions API.
- Temperature: `0.1` as the initial setting requested by the owner. If an API/model rejects a parameter, handle that documented error and do not silently alter the model.
- Model ID must be an environment variable with the specified value as default.
- The model is currently listed in Groq's supported model catalogue. Its API documentation publishes token pricing and account-level rate limits; do not promise unlimited free calls.

**Fallback provider:** OpenRouter.

- Base URL: `https://openrouter.ai/api/v1`
- Use a configurable `OPENROUTER_MODEL`, with `openrouter/free` as the initial free-routing choice or a verified free model ID.
- Free models are rate-limited and availability can change. The fallback is best-effort, not a service-level guarantee.
- Do not automatically buy credits or switch to a paid model.
- Fallback for transient network errors, timeouts, HTTP 429, or HTTP 5xx. Do not disguise a bad API key, missing configuration, invalid request, or malformed response as a normal fallback success; log a safe error code and return an actionable message if both providers fail.

### 2.5 PDF processing

- Use PyMuPDF; do not use OCR in the MVP.
- Extract page-by-page so every chunk can cite a 1-based page number.
- Normalize repeated whitespace without flattening all paragraphs into one unreadable string.
- Target 500 characters per chunk and 50 characters overlap.
- Prefer sentence/paragraph boundaries where practical; enforce a maximum chunk length to avoid very long chunks.
- Detect PDFs with no usable text and return an explicit error explaining that scanned PDFs/OCR are not supported yet.
- Configure maximum upload size and page count. Suggested initial limits: 20 MB and 200 pages; keep both environment-configurable.

## 3. Hosting decision and free-tier reality check

### 3.1 Frontend: Vercel Hobby

**Recommendation:** Retain Vercel Hobby for the Next.js frontend.

- Suitable for student prototypes, personal projects, and small apps.
- Configure `NEXT_PUBLIC_API_URL` in the Vercel project environment variables.
- Deploy preview and production environments separately.
- Usage is subject to Hobby plan quotas and platform terms. Monitor usage; do not assume unlimited traffic or compute.

Official references:
- https://vercel.com/docs/plans/hobby
- https://vercel.com/docs/limits

### 3.2 Preferred backend: Hugging Face Spaces ZeroGPU

**Selected target:** Hugging Face Spaces using the Gradio SDK and ZeroGPU.

- ZeroGPU dynamically allocates GPU resources only while a registered `@spaces.GPU` Gradio event is running. The app's embedding function must be both decorated and bound as a Gradio event; an unused decorated helper does not satisfy the ZeroGPU startup check.
- Place the embedding model on CUDA during module initialization in the ZeroGPU environment, and keep local development on CPU. The Hugging Face `requirements.txt` must not force-install CPU-only PyTorch; the local Docker setup can select a CPU wheel separately.
- The Vercel frontend continues to use the existing REST API hosted by this Space. Keep the FastAPI routes and configure `NEXT_PUBLIC_API_URL` to the Space URL.
- Default disk is not persistent. Store canonical vectors and metadata in Supabase, not in the Space container filesystem.
- ZeroGPU has account-dependent daily quotas and queue times. Surface cold starts and do not assume unlimited GPU access.
- Store secrets in Space Settings → Secrets, not in the repository.

**Decision:** Keep the existing Hugging Face ZeroGPU target. Do not switch hardware or enable paid compute without the owner's approval.

Official references:
- https://huggingface.co/docs/hub/spaces-overview
- https://huggingface.co/docs/hub/spaces-zerogpu
- https://huggingface.co/docs/huggingface_hub/guides/manage-spaces
- https://huggingface.co/pricing

### 3.3 Optional no-subscription alternative: Render Free Web Service

Render currently allows free web services for Python applications, including FastAPI. This is a practical alternative for a low-volume demo, but it has meaningful restrictions:

- It spins down after 15 minutes without inbound HTTP/WebSocket activity; the next request can take about one minute to wake it.
- Free service filesystems are ephemeral. Do not store uploaded PDFs or important data on local disk.
- It has a monthly free-instance-hours allowance and service restarts are possible.
- Render explicitly says free instances are intended for testing/hobby projects, not production.
- The CPU/RAM and build constraints may make a PyTorch/sentence-transformers container awkward. Measure memory and cold-start time before choosing it.

This is an alternative only if the owner approves changing the backend host from Hugging Face to Render.

Official references:
- https://render.com/docs/free
- https://render.com/docs/faq

### 3.4 Optional alternative: Google Cloud Run

Cloud Run has a usage-based free tier that includes monthly CPU, memory, request, and outbound-traffic allowances, subject to region and billing configuration. It can run the FastAPI Docker container and can be a stronger container hosting option than a small hobby runtime.

However, a Google Cloud billing account is generally required, and usage above the free tier can incur charges. It is not a guaranteed zero-risk “free forever” host. Use budget alerts and explicit owner approval before selecting it.

Official references:
- https://cloud.google.com/run/pricing
- https://cloud.google.com/free/docs/free-cloud-features

### 3.5 Database: Supabase Free

**Recommendation:** Retain Supabase Free for the MVP.

Current published Free-plan allowances include:

- 500 MB database size per project.
- 1 GB file storage.
- 5 GB egress and 5 GB cached egress.
- 50,000 monthly active users.
- Free projects may be paused after one week of inactivity.
- A maximum of two active free projects is listed.

The project stores chunk text and vectors in Postgres, not the original PDF file, so the 1 GB object-storage quota is not required for the initial design. Embedding vectors still consume database storage; monitor growth.

Use the backend-only Supabase service-role key. Never expose this key to the frontend. Enable RLS and grant access only to the backend service role for the MVP table/RPC.

Official embedding reference:
- https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2

Official Supabase references:
- https://supabase.com/pricing
- https://supabase.com/docs/guides/platform/billing-on-supabase
- https://supabase.com/docs/guides/database/extensions/pgvector

### 3.6 LLM: Groq Free Plan + OpenRouter fallback

**Primary:** `openai/gpt-oss-120b` on Groq.

- Current Groq model catalogue lists this model as supported.
- Groq supports the OpenAI client pattern by setting `base_url` to `https://api.groq.com/openai/v1`.
- The model has published token pricing on Groq's model page. The free plan has model-specific rate limits; the current rate-limit documentation lists 30 RPM, 1,000 requests/day, 8,000 TPM, and 200,000 TPD for `openai/gpt-oss-120b` on the Free Plan. The exact account limit can differ and must be checked in the Groq console.
- Do not use `llama-3.3-70b` as the selected model. The application must use the requested GPT-OSS model ID unless the owner approves a change.

**Fallback:** OpenRouter free models.

- OpenRouter offers free model routes/variants, including the `openrouter/free` router.
- Free model access is rate-limited and availability/provider routing can change. The current free-model collection describes a 50 requests/day baseline for free variants (and a 20 requests/minute cap); limits may vary by account and model.
- Treat this as fallback availability, not a guaranteed backup SLA.

Official references:
- https://console.groq.com/docs/models
- https://console.groq.com/docs/model/openai/gpt-oss-120b
- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/openai
- https://openrouter.ai/collections/free-models
- https://openrouter.ai/pricing

## 4. Recommended environment variables

### Backend `.env`

```dotenv
# Primary LLM
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
GROQ_BASE_URL=https://api.groq.com/openai/v1

# Fallback LLM
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openrouter/free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Supabase: use the server-side service_role key only
SUPABASE_URL=
SUPABASE_KEY=

# Signed anonymous workspace tokens
SESSION_SECRET=
SESSION_TTL_HOURS=168

# PDF + RAG settings
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
CHUNK_SIZE=500
CHUNK_OVERLAP=50
TOP_K=4
MIN_SIMILARITY=
MAX_UPLOAD_MB=20
MAX_PDF_PAGES=200

# CORS: comma-separated exact origins
CORS_ORIGINS=http://localhost:3000

# Optional; only needed for gated/private model assets or Hub API use
HF_TOKEN=
```

`MIN_SIMILARITY` must be calibrated using a small evaluation set of questions that are both answerable and unanswerable from representative PDFs. Do not assume one universal threshold is correct for every document.

### Frontend `.env.local`

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8001
```

On Vercel, replace the value with the deployed backend URL. No backend provider key belongs in the frontend environment.

## 5. Security and configuration rules

1. `.env`, `.env.local`, host secret files, service-role keys, and provider keys must be ignored by Git.
2. Commit only `.env.example` with empty values and descriptions.
3. The Supabase service-role key is server-only. Do not use it in a `NEXT_PUBLIC_` variable.
4. Hugging Face secrets are configured in Space Settings → Secrets.
5. Vercel frontend receives only `NEXT_PUBLIC_API_URL`.
6. Never print secrets in logs or API responses.
7. CORS must use the exact local and production frontend origins, not `*` with credentials.
8. Add upload size/page limits, timeouts, request validation and rate limiting.
9. A PDF may contain prompt-injection text. The RAG prompt must explicitly treat retrieved PDF passages as untrusted reference material, not as instructions.
10. No paid plan, compute upgrade, model credit purchase, or alternative host may be enabled without owner approval.

## 6. Final recommendation

For the requested stack, retain **Next.js + Vercel, FastAPI REST API in a Hugging Face Gradio-SDK ZeroGPU Space, Supabase pgvector, all-MiniLM-L6-v2 embeddings, Groq GPT-OSS 120B, and OpenRouter free fallback**.

The biggest practical caveats are ZeroGPU account eligibility, daily quota, and queue time. Do not alter the selected hardware or deploy to a different provider automatically.
