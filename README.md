# PDF RAG Assistant

A document-grounded study assistant. Admins can group multiple PDFs under a lesson or add standalone knowledge-base PDFs; the backend indexes them for cited answers. Students can save and reopen chats in the current browser and attach images for visual analysis when the configured Groq or OpenRouter model supports vision.

## Project documents

- [`PROJECT_SCOPE.md`](PROJECT_SCOPE.md) — product objectives, scope, boundaries, requirements, risks, and acceptance criteria.
- [`TECH_STACK.md`](TECH_STACK.md) — selected stack, hosting analysis, free-tier caveats, environment variables, and security decisions.
- [`IMPLEMENTATION_GUIDE.md`](IMPLEMENTATION_GUIDE.md) — exact three-phase build order, file structure, tasks, and test commands.
- [`API_CONTRACT.md`](API_CONTRACT.md) — backend request/response contract.
- [`PROMPT.md`](PROMPT.md) — master prompt to give an AI coding agent.
- [`database/schema.sql`](database/schema.sql) — Supabase pgvector schema and similarity-search RPC.
- [`.env.example`](.env.example) — safe environment-variable template with blank values.

## Required development order

1. **Phase 1 — PDF extraction and chunking.** No LLM and no vector database. Test first, then stop for owner approval.
2. **Phase 2 — Embeddings and Supabase pgvector.** Store and search chunks. Test workspace isolation and retrieval, then stop for approval.
3. **Phase 3 — RAG generation, frontend integration, and deployment.** Implement Groq/OpenRouter, citations, abstention, UI, Docker, and final tests.

The AI agent must not skip a phase or implement all phases in one pass. It must not move to the next phase without explicit approval.

## Quick start for an AI coding agent

1. Create/clone the project repository.
2. Copy the project documents and `database/schema.sql` into the repository root using this folder structure.
3. Open the repository root in the coding agent.
4. Paste the complete contents of `PROMPT.md` as the project-level instruction (or point the agent to the file and explicitly ask it to read it).
5. Ask it to begin **Phase 1 only**.
6. Review the implementation and test output before approving Phase 2.

## Run locally without Docker

The backend runs on FastAPI/Uvicorn and the frontend on Next.js. Docker is not required for local development.

1. In PowerShell, create local environment files only if they do not already exist. Do not overwrite your existing ignored files:

   ```powershell
   if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }
   if (-not (Test-Path frontend\.env.local)) { Copy-Item frontend\.env.local.example frontend\.env.local }
   ```

2. Set `GROQ_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, a strong `SESSION_SECRET`, and `ADMIN_EMAIL`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD` in `backend\.env`. `SUPABASE_KEY` must be the server-side secret key. Keep all credentials in this backend-only file; do not put them in the frontend. Admin sign-in is available at `/login`; `/admin` redirects unauthenticated visitors to sign-in.
3. Ensure the Supabase project has the SQL in `database/schema.sql` applied. This sets up the pgvector extension, `documents` table, `match_documents` RPC, and multi-PDF lesson metadata. Reapply it to existing projects to add and backfill the lesson document list.
4. Start the backend in one PowerShell terminal:

   ```powershell
   Set-Location backend
   .\.venv\Scripts\Activate.ps1
   uvicorn app:app --reload --host 127.0.0.1 --port 8001
   ```

   If you do not have a backend virtual environment yet, create one and install the requirements first:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple torch==2.8.0
   python -m pip install -r requirements.txt
   ```

5. Start the frontend in a second PowerShell terminal:

   ```powershell
   Set-Location frontend
   npm run dev
   ```

6. Open `http://localhost:3000`. The backend health endpoint is `http://127.0.0.1:8001/health`.

Chat history is stored in this browser only; it is not synchronized between devices. Image analysis uses the existing provider configuration and requires a vision-capable `GROQ_MODEL` or `OPENROUTER_MODEL`.

Run backend tests from `backend\` with `pytest -q` and build the frontend from `frontend\` with `npm run build`. The current `npm run lint` command opens Next.js's ESLint setup prompt because no ESLint configuration is present yet.

## Deploy Vercel frontend with the Hugging Face ZeroGPU Space

The Hugging Face Space uses the **Gradio SDK with ZeroGPU**. The app keeps its existing FastAPI REST endpoints (used by the Vercel frontend) and mounts a small Gradio page. Do not replace the FastAPI endpoints with Gradio's queued event API: uploads, chat, lessons, admin, and promo-code flows depend on the existing REST contract.

1. Deploy the contents of `backend\` to the root of the Space repository, preserving the Space README front matter and its Gradio SDK/ZeroGPU settings. The Space's `requirements.txt` must include `spaces` and `torch>=2.8.0`; do not install CPU-only PyTorch there. The local Dockerfile installs CPU-only PyTorch separately for local/container development.
2. In Space Settings → Variables and Secrets, configure the required backend values: `SESSION_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `SUPABASE_URL`, `SUPABASE_KEY`, `GROQ_API_KEY`, and `CORS_ORIGINS`. `OPENROUTER_API_KEY` is optional. Set `CORS_ORIGINS` to the exact comma-separated frontend origins, for example `https://your-project.vercel.app,https://www.example.com`; only those origins will be allowed when this variable is configured. Keep provider and Supabase keys as Space secrets.
3. In the Vercel project settings, set `NEXT_PUBLIC_API_URL` to the Space URL, for example `https://adrame-ai-bot-diploma.hf.space`, then redeploy. This value is public and must contain no credentials.
4. Verify the Space starts without the `No @spaces.GPU function detected during startup` error, then check `https://<space-host>/health` returns JSON. The Gradio page at `/gradio` includes a ZeroGPU embedding check. Finally verify the Vercel app can create a session, upload a PDF, ask questions, and use the admin/lesson/promo flows.

ZeroGPU quotas and queue times vary by account tier. The app uses Supabase for persistent vector data; Hugging Face's local container disk is not a durable store. Never paste Hugging Face, Supabase, or provider tokens into chat or commit them to the repository.

## Free-tier note

The target stack is designed for a small prototype. Free-tier eligibility, ZeroGPU quotas, and queue times can change. See `TECH_STACK.md` before changing hosting or enabling paid compute.

## Security note

- Never commit `.env`, `.env.local`, provider API keys, or Supabase service-role keys.
- Keep Supabase service-role credentials in the backend only.
- Only the public backend URL belongs in `NEXT_PUBLIC_API_URL`.
- Do not upload private course material to a public source repository.

## Important limitation

Prompting an LLM to use only retrieved PDF text does not mathematically guarantee zero hallucinations. This project reduces unsupported answers through evidence thresholds, citation validation, explicit abstention, and adversarial tests. The UI must never claim an absolute zero-hallucination guarantee.
