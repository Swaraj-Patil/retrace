-- Initial ClickHouse schema for Retrace.
-- Generic OTel-shaped traces table + three RAG-specific additive tables.
-- All RAG tables carry project_id and put it first in ORDER BY so per-project
-- queries hit the primary index.

CREATE TABLE IF NOT EXISTS traces
(
    trace_id        UUID,
    span_id         UUID,
    parent_span_id  Nullable(UUID),
    project_id      UUID,
    start_time      DateTime64(3, 'UTC'),
    end_time        DateTime64(3, 'UTC'),
    latency_ms      UInt32,
    model           LowCardinality(String),
    tokens_in       UInt32,
    tokens_out      UInt32,
    status          LowCardinality(String),
    attributes      String  -- JSON-encoded; will become JSON type once stable
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(start_time)
ORDER BY (project_id, trace_id, start_time)
-- TTL start_time + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 8192;


CREATE TABLE IF NOT EXISTS retrievals
(
    retrieval_id     UUID,
    trace_id         UUID,
    span_id          UUID,
    project_id       UUID,
    query            String,
    embedding_model  LowCardinality(String),
    top_k            UInt16,
    latency_ms       UInt32,
    timestamp        DateTime64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (project_id, trace_id, retrieval_id)
-- TTL timestamp + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 8192;


CREATE TABLE IF NOT EXISTS retrieved_chunks
(
    chunk_id          UUID,
    retrieval_id      UUID,
    project_id        UUID,
    rank              UInt16,
    similarity_score  Float32,
    content           String,
    source_doc_id     String,
    doc_metadata      String,  -- JSON-encoded
    timestamp         DateTime64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (project_id, retrieval_id, rank)
-- TTL timestamp + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 8192;


CREATE TABLE IF NOT EXISTS citations
(
    citation_id           UUID,
    trace_id              UUID,
    chunk_id              UUID,
    project_id            UUID,
    response_span_start   UInt32,
    response_span_end     UInt32,
    timestamp             DateTime64(3, 'UTC')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (project_id, trace_id, citation_id)
-- TTL timestamp + INTERVAL 90 DAY DELETE
SETTINGS index_granularity = 8192;
