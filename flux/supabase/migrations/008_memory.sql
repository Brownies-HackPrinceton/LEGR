-- Enable pgvector (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- Table for short-term iMessage chat history
CREATE TABLE IF NOT EXISTS message_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    chat_id TEXT NOT NULL,       -- Usually the phone number or distinct thread ID
    role TEXT NOT NULL,          -- 'user' or 'assistant'
    content TEXT NOT NULL,       -- The actual message text
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for fast lookup of chat threads
CREATE INDEX IF NOT EXISTS idx_message_history_chat_id ON message_history(chat_id, created_at ASC);

-- Table for long-term extracted memories to feed RAG
CREATE TABLE IF NOT EXISTS memories (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1536),      -- text-embedding-3-small uses 1536 dims
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for pgvector searches (optional but good practice for larger data sets)
-- Using HNSW for cosine similarity
CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories USING hnsw (embedding vector_cosine_ops);

-- RPC function for matching memories using cosine distance (<=>)
CREATE OR REPLACE FUNCTION match_memories(
    query_embedding vector(1536),
    match_threshold float,
    match_count int,
    p_company_id uuid
)
RETURNS TABLE (
    id uuid,
    content text,
    similarity float
)
LANGUAGE sql STABLE
AS $$
    SELECT
        id,
        content,
        1 - (embedding <=> query_embedding) AS similarity
    FROM memories
    WHERE company_id = p_company_id
      AND 1 - (embedding <=> query_embedding) > match_threshold
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;
