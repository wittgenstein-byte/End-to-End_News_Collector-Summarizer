CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prefs JSONB DEFAULT '{}'::jsonb,
    read_hist UUID[] DEFAULT '{}',
    categories TEXT[] DEFAULT '{}',
    sources TEXT[] DEFAULT '{}',
    bookmarks UUID[] DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS articles (
    id UUID DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    summary TEXT,
    category TEXT,
    source_url TEXT,
    pub_at TIMESTAMPTZ NOT NULL,
    vector_emb VECTOR(1536),
    PRIMARY KEY (id, pub_at)
) PARTITION BY RANGE (pub_at);

CREATE TABLE IF NOT EXISTS articles_y2025 PARTITION OF articles
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');

CREATE TABLE IF NOT EXISTS articles_y2026 PARTITION OF articles
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE TABLE IF NOT EXISTS articles_default PARTITION OF articles DEFAULT;

CREATE INDEX IF NOT EXISTS idx_articles_source_url ON articles(source_url);
CREATE INDEX IF NOT EXISTS idx_articles_vector ON articles USING hnsw (vector_emb vector_cosine_ops);
