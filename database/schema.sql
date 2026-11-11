-- PDF RAG Assistant — Supabase PostgreSQL + pgvector schema
-- Run this file in the Supabase SQL Editor after selecting the correct project.
-- One row represents one extracted text chunk, not one entire PDF.
-- Keep the service-role key on the backend only.

create extension if not exists vector with schema extensions;

create table if not exists public.documents (
    id uuid primary key default gen_random_uuid(),

    -- Groups all chunks belonging to one uploaded PDF.
    document_id uuid not null,

    -- Derived from a signed backend-issued workspace token.
    workspace_id uuid not null,

    content text not null,
    embedding extensions.vector(384) not null,
    metadata jsonb not null default '{}'::jsonb,
    pdf_name text not null,

    -- First-class columns are useful for filtering and citations.
    page_number integer not null check (page_number >= 1),
    chunk_index integer not null check (chunk_index >= 0),
    created_at timestamptz not null default now(),

    constraint documents_unique_chunk
        unique (workspace_id, document_id, chunk_index)
);

create index if not exists documents_workspace_document_idx
    on public.documents (workspace_id, document_id);

create index if not exists documents_created_at_idx
    on public.documents (created_at desc);

-- HNSW index for cosine-distance search. For a very small dataset, exact
-- search may be sufficient; benchmark before changing index strategy.
create index if not exists documents_embedding_cosine_idx
    on public.documents
    using hnsw (embedding extensions.vector_cosine_ops);

-- RLS is enabled. Backend accesses the table using the server-only
-- service_role key. Do not expose that key to the frontend.
alter table public.documents enable row level security;

revoke all on table public.documents from anon, authenticated;
grant select, insert, delete on table public.documents to service_role;

-- Search function. workspace_id and document_id must be passed by the
-- backend after validating the signed workspace token. The RPC filters in
-- SQL so chunks from another workspace/document cannot enter the result set.
create or replace function public.match_documents(
    query_embedding extensions.vector(384),
    match_count integer,
    filter_workspace_id uuid,
    filter_document_id uuid
)
returns table (
    id uuid,
    document_id uuid,
    pdf_name text,
    content text,
    metadata jsonb,
    page_number integer,
    chunk_index integer,
    similarity double precision
)
language sql
stable
security invoker
set search_path = public, extensions
as $$
    select
        d.id,
        d.document_id,
        d.pdf_name,
        d.content,
        d.metadata,
        d.page_number,
        d.chunk_index,
        (1 - (d.embedding <=> query_embedding))::double precision as similarity
    from public.documents as d
    where d.workspace_id = filter_workspace_id
      and d.document_id = filter_document_id
    order by d.embedding <=> query_embedding
    limit greatest(1, least(coalesce(match_count, 4), 20));
$$;

revoke all on function public.match_documents(
    extensions.vector(384), integer, uuid, uuid
) from public, anon, authenticated;

grant execute on function public.match_documents(
    extensions.vector(384), integer, uuid, uuid
) to service_role;

-- Optional manual check after inserting sample rows:
-- select id, pdf_name, page_number, chunk_index
-- from public.documents
-- order by created_at desc
-- limit 10;


-- ----------------------------------------------------------------------------
-- Lessons table for organizing course content and knowledge bases
-- ----------------------------------------------------------------------------
create table if not exists public.lessons (
    id uuid primary key default gen_random_uuid(),
    title text not null,
    description text default '',
    workspace_id uuid not null default '00000000-0000-0000-0000-000000000001'::uuid,
    document_id uuid,
    pdf_name text,
    pages_count integer default 0,
    chunks_count integer default 0,
    documents jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

alter table public.lessons
    add column if not exists documents jsonb not null default '[]'::jsonb;

-- Preserve the existing single-PDF association when upgrading older projects.
update public.lessons
set documents = jsonb_build_array(jsonb_build_object(
    'document_id', document_id::text,
    'pdf_name', coalesce(pdf_name, 'document.pdf'),
    'pages_count', coalesce(pages_count, 0),
    'chunks_count', coalesce(chunks_count, 0)
))
where document_id is not null
  and jsonb_array_length(documents) = 0;

alter table public.lessons enable row level security;
revoke all on table public.lessons from anon, authenticated;
grant select, insert, update, delete on table public.lessons to service_role;
