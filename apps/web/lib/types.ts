/**
 * Read-API response shapes. Mirrors apps/api/api/schemas/read.py
 * field-for-field. Keep in sync manually for now - codegen later.
 *
 * Date/time values come over the wire as ISO 8601 strings; this layer
 * keeps them as strings rather than parsing to Date so server and
 * client agree on the value and there's no timezone surprise.
 */

export type TraceStatus = "ok" | "OK" | "error" | "ERROR" | string;

export interface TraceListItem {
  trace_id: string;
  start_time: string;
  model: string;
  latency_ms: number;
  tokens_in: number;
  tokens_out: number;
  status: TraceStatus;
  has_retrieval: boolean;
  chunk_count: number;
  citation_count: number;
}

export interface TraceListResponse {
  traces: TraceListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface TraceMeta {
  trace_id: string;
  start_time: string;
  model: string;
  latency_ms: number;
  tokens_in: number;
  tokens_out: number;
  status: TraceStatus;
  attributes: Record<string, unknown>;
}

export interface ChunkDetail {
  chunk_id: string;
  rank: number;
  similarity_score: number;
  content: string;
  source_doc_id: string;
  doc_metadata: Record<string, unknown>;
  was_cited: boolean;
}

export interface RetrievalDetail {
  retrieval_id: string;
  query: string;
  embedding_model: string;
  top_k: number;
  latency_ms: number;
  chunks: ChunkDetail[];
}

export interface CitationDetail {
  citation_id: string;
  chunk_id: string;
  response_span_start: number;
  response_span_end: number;
}

export interface TraceDetailResponse {
  trace: TraceMeta;
  retrievals: RetrievalDetail[];
  citations: CitationDetail[];
}

export interface TracesOverTimePoint {
  date: string;
  count: number;
}

export interface ScoreBucket {
  bucket: string;
  count: number;
}

export interface MetricsOverviewResponse {
  total_traces: number;
  rag_traces: number;
  avg_retrieval_latency_ms: number;
  chunks_never_cited_rate: number;
  avg_top_similarity: number;
  citation_coverage: number;
  traces_over_time: TracesOverTimePoint[];
  score_distribution: ScoreBucket[];
}

// Query param shapes consumed by the API client.

export interface ListTracesParams {
  limit?: number;
  offset?: number;
  rag_only?: boolean;
  from?: string;
  to?: string;
}

export interface MetricsParams {
  from?: string;
  to?: string;
}

// Auth + console shapes. Mirrors apps/api/api/schemas/auth.py and
// apps/api/api/schemas/console.py field-for-field.

export interface SessionTokenResponse {
  token: string;
  /** ISO 8601 timestamp; ``new Date(expires_at)`` is safe for the
   *  cookie ``expires`` option. */
  expires_at: string;
}

export interface OrgRef {
  id: string;
  name: string;
  slug: string;
  /** ``owner`` | ``admin`` | ``member`` from the membership table. */
  role: string;
}

export interface MeResponse {
  user_id: string;
  email: string;
  name: string | null;
  orgs: OrgRef[];
}
