"""Seed local dev databases with a demo org, project, API key, and a
richer telemetry dataset (75 traces over ~18 days).

Idempotent: rerunning wipes the demo org (and its cascade) plus all
ClickHouse trace rows tagged with the demo project_id, then re-inserts
fresh data.

Deterministic content: a single seeded ``random.Random(42)`` drives
every random choice, and trace/retrieval/chunk/citation IDs are derived
from ``uuid5(SEED_NS, "kind-i-j")`` so re-running produces identical
IDs. Timestamps are anchored to "now" so relative-time labels in the
dashboard stay current; that means daily-count bucket positions shift
across the x-axis between re-seeds, but the SHAPE of the histogram and
the distribution of every other metric stay byte-identical.

The dataset is tuned so chunks_never_cited_rate lands near 73% on a
fresh seed - that's the headline number on the dashboard and the
load-bearing demo signal.

Usage:
    uv run python scripts/seed.py
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_DNS, UUID, uuid5

from sqlalchemy import delete

from api.clickhouse.client import get_client
from api.db.session import SessionLocal, engine
from api.models import (
    ApiKey,
    Membership,
    MembershipRole,
    Org,
    Project,
    User,
)
from api.security import generate_api_key

DEMO_ORG_SLUG = "demo"
DEMO_USER_EMAIL = "demo@retrace.dev"
DEMO_PROJECT_SLUG = "demo-project"

# Deterministic UUID for the demo project so ClickHouse cleanup by
# project_id matches the previous run's data on every reseed.
DEMO_PROJECT_ID = uuid5(NAMESPACE_DNS, "demo-project.retrace.dev")

# Mixed model distribution. Weighted so the demo reads as a real
# project using a couple of vendors, with one dominant model.
MODEL_WEIGHTS: list[tuple[str, float]] = [
    ("gpt-4o", 0.40),
    ("gpt-4o-mini", 0.15),
    ("gpt-4", 0.15),
    ("claude-3-5-sonnet-20241022", 0.20),
    ("claude-3-haiku-20240307", 0.10),
]
EMBED_MODELS = [
    "text-embedding-3-small",
    "text-embedding-3-large",
    "voyage-3",
    "voyage-3-lite",
]

SAMPLE_QUERIES = [
    "How do I configure retries in the SDK?",
    "What does retrieval_score below 0.4 mean?",
    "Show me the steps to enable citations.",
    "Where is the dashboard hosted?",
    "How do I rotate an API key?",
    "What's the difference between manual and auto-instrumentation?",
    "Can I capture custom attributes per trace?",
    "How are chunks stored and queried?",
    "What does chunks_never_cited_rate actually measure?",
    "How do I run the SDK against a local backend?",
    "Is there a Python SDK for Anthropic?",
    "How do I batch retrievals?",
    "What's the trace retention policy?",
    "Does Retrace support multi-tenant deployments?",
    "How are response spans computed?",
    "What's a reasonable chunk size for embeddings?",
    "Can I see uncited chunks in the dashboard?",
    "How does the SDK detect retrievals?",
    "What's a healthy avg_top_similarity?",
    "Where do I find demo data for testing?",
]

SAMPLE_CHUNKS = [
    "Retries are configured via the `RetryPolicy` argument on `Client(...)`.",
    "Retrieval scores below 0.4 typically indicate the query had no good match in the index.",
    "To enable citations, call `record_citation(chunk_id, start, end)` after generation.",
    "The hosted demo runs on Fly.io and is exposed at demo.retrace.dev.",
    "API keys can be rotated from the project settings page; old keys remain valid for 24h.",
    "Each retrieval span captures top_k, embedding_model, and per-chunk similarity scores.",
    "Citations link a response span back to the chunk that supplied the supporting text.",
    "The default embedding model can be overridden per-call via the `embedding_model` kwarg.",
    "Auto-instrumentation patches the OpenAI and Anthropic SDKs at import time.",
    "Manual RAG instrumentation uses `retrace.retrieval()` and `retrace.log_chunk()`.",
    "Chunks are stored in ClickHouse with project_id as the leading sort key.",
    "Citations are validated against retrieved_chunks in-batch via FK closure.",
    "The SDK buffers events in memory and flushes asynchronously in batches.",
    "Each batch is up to 1000 items; larger batches are rejected with 413.",
    "project_id is derived from the API key on the server, never client-supplied.",
    "Traces are partitioned monthly in ClickHouse for efficient retention queries.",
    "chunks_never_cited_rate is the fraction of retrieved chunks that never appear in any citation.",
    "Score distribution buckets are 0.1 wide; values at exactly 1.0 land in the 0.9-1.0 bucket.",
    "Anthropic Messages uses input_tokens/output_tokens; OpenAI uses prompt_tokens/completion_tokens.",
    "Retrace never captures message content - only retrieval and citation metadata.",
]

TOP_K_OPTIONS: list[int] = [3, 4, 5, 6, 7, 8, 10]

# Per-RAG-trace number of citations, tuned so the dashboard's default
# 7-day window lands at ~72% chunks_never_cited_rate. The mean here
# (~1.95 citations/trace) compensates for the small-sample noise the
# 7d window adds on top of the all-time signal; lower mean drove the
# windowed view above 75% in earlier iterations.
CITATION_COUNT_WEIGHTS: list[tuple[int, float]] = [
    (0, 0.10),
    (1, 0.30),
    (2, 0.30),
    (3, 0.20),
    (4, 0.10),
]

NUM_RAG_TRACES = 45
NUM_PLAIN_TRACES = 30
DAYS_SPAN = 18
RNG_SEED = 42

# Stable namespace for trace/retrieval/chunk/citation ids. Independent
# of the demo project_id so re-running with a different project (e.g.
# in a fork) still produces identical row IDs for screenshots.
SEED_NS = uuid5(NAMESPACE_DNS, "demo-seed.retrace.dev")


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def seed_postgres() -> tuple[UUID, str]:
    """Seed Postgres. Return (project_id, raw_api_key)."""
    async with SessionLocal() as session:
        # Idempotency: drop the demo org (cascades to membership/project/api_keys)
        # and the demo user (independent of the org's cascade).
        await session.execute(delete(Org).where(Org.slug == DEMO_ORG_SLUG))
        await session.execute(delete(User).where(User.email == DEMO_USER_EMAIL))
        await session.commit()

        org = Org(name="Demo Org", slug=DEMO_ORG_SLUG)
        user = User(email=DEMO_USER_EMAIL, name="Demo User")
        session.add_all([org, user])
        await session.flush()

        membership = Membership(org_id=org.id, user_id=user.id, role=MembershipRole.OWNER)
        project = Project(
            id=DEMO_PROJECT_ID,
            org_id=org.id,
            name="Demo Project",
            slug=DEMO_PROJECT_SLUG,
        )
        session.add_all([membership, project])
        await session.flush()

        generated = generate_api_key()
        api_key = ApiKey(
            project_id=project.id,
            name="Default key",
            key_prefix=generated.prefix,
            hashed_key=generated.hashed,
        )
        session.add(api_key)
        await session.commit()

        return project.id, generated.raw


def _clear_clickhouse_for_project(project_id: UUID) -> None:
    client = get_client()
    pid = str(project_id)
    # mutations_sync=2 makes the DELETE wait for the mutation to complete
    # before returning. Without it, fresh INSERTs can land before the old rows
    # are gone, producing duplicate seed data across reruns.
    for table in ("traces", "retrievals", "retrieved_chunks", "citations"):
        client.command(
            f"ALTER TABLE {table} DELETE WHERE project_id = %(pid)s",
            parameters={"pid": pid},
            settings={"mutations_sync": 2},
        )


def _id(kind: str, *parts: object) -> UUID:
    """Deterministic per-row UUID. Same (kind, parts) tuple always
    produces the same UUID, across re-seeds and across machines."""
    return uuid5(SEED_NS, f"{kind}:" + ":".join(str(p) for p in parts))


def _weighted_pick(rng: random.Random, items_and_weights: list[tuple]) -> object:
    items = [i for i, _ in items_and_weights]
    weights = [w for _, w in items_and_weights]
    return rng.choices(items, weights=weights, k=1)[0]


def _pick_model(rng: random.Random) -> str:
    return _weighted_pick(rng, MODEL_WEIGHTS)  # type: ignore[return-value]


def _vendor_of(model: str) -> str:
    """Loose vendor extraction for the attributes blob - cosmetic only."""
    if model.startswith("gpt"):
        return "openai"
    if model.startswith("claude"):
        return "anthropic"
    return "other"


def _make_plain_trace(
    rng: random.Random, idx: int, project_id: UUID, when: datetime
) -> dict[str, object]:
    model = _pick_model(rng)
    tokens_in = rng.randint(120, 1200)
    tokens_out = rng.randint(50, 600)
    latency_ms = rng.randint(400, 3500)
    return {
        "trace_id": _id("trace", idx),
        "span_id": _id("span", idx),
        "parent_span_id": None,
        "project_id": project_id,
        "start_time": when,
        "end_time": when + timedelta(milliseconds=latency_ms),
        "latency_ms": latency_ms,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "status": "OK",
        "attributes": json.dumps({"kind": "llm.chat", "vendor": _vendor_of(model)}),
    }


def _make_rag_flow(
    rng: random.Random,
    idx: int,
    project_id: UUID,
    when: datetime,
) -> tuple[
    dict[str, object],
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    """Build one RAG trace + its retrieval + N chunks + M citations.

    Score generation: per-retrieval base in [0.5, 0.95], per-chunk
    decay of 0.05 per rank, plus +/- 0.05 jitter. Clamps to [0, 1].
    This produces a real distribution across 6-8 buckets of the
    score-distribution histogram rather than a single spike.

    Citation pattern: 85% of traces cite from the top-3 chunks, 15%
    extend to top-5 for variety. Number of citations per trace is
    weighted (0/1/2/3/4) to land near 73% chunks_never_cited_rate
    against the rest of the distribution.
    """
    model = _pick_model(rng)
    latency_ms = rng.randint(600, 4500)
    trace_id = _id("trace", idx)
    retrieval_id = _id("retrieval", idx)
    top_k = rng.choice(TOP_K_OPTIONS)

    trace = {
        "trace_id": trace_id,
        "span_id": _id("span", idx),
        "parent_span_id": None,
        "project_id": project_id,
        "start_time": when,
        "end_time": when + timedelta(milliseconds=latency_ms),
        "latency_ms": latency_ms,
        "model": model,
        # RAG traces send the retrieved context with the prompt, so
        # tokens_in skews higher than plain.
        "tokens_in": rng.randint(900, 3200),
        "tokens_out": rng.randint(60, 700),
        "status": "OK",
        "attributes": json.dumps(
            {"kind": "rag.qa", "vendor": _vendor_of(model), "top_k": top_k}
        ),
    }

    retrieval = {
        "retrieval_id": retrieval_id,
        "trace_id": trace_id,
        "span_id": _id("retrieval-span", idx),
        "project_id": project_id,
        "query": rng.choice(SAMPLE_QUERIES),
        "embedding_model": rng.choice(EMBED_MODELS),
        "top_k": top_k,
        "latency_ms": rng.randint(40, 380),
        "timestamp": when,
    }

    base_score = rng.uniform(0.5, 0.95)
    chunk_rows: list[dict[str, object]] = []
    for rank in range(top_k):
        score = base_score - 0.05 * rank + rng.uniform(-0.05, 0.05)
        score = max(0.0, min(1.0, score))
        chunk_rows.append(
            {
                "chunk_id": _id("chunk", idx, rank),
                "retrieval_id": retrieval_id,
                "project_id": project_id,
                "rank": rank,
                "similarity_score": round(score, 4),
                "content": rng.choice(SAMPLE_CHUNKS),
                "source_doc_id": f"doc_{rng.randint(100, 999)}",
                "doc_metadata": json.dumps(
                    {
                        "title": f"Docs page {rng.randint(1, 50)}",
                        "url": "https://docs.retrace.dev",
                    }
                ),
                "timestamp": when,
            }
        )

    # Citations: pick a candidate pool then sample without replacement.
    num_citations: int = _weighted_pick(rng, CITATION_COUNT_WEIGHTS)  # type: ignore[assignment]
    pool_size = min(5 if rng.random() >= 0.85 else 3, top_k)
    n_to_cite = min(num_citations, pool_size)
    cited_indices = rng.sample(range(pool_size), n_to_cite) if n_to_cite > 0 else []
    citation_rows: list[dict[str, object]] = []
    cursor = 0
    for j, chunk_rank in enumerate(cited_indices):
        span_len = rng.randint(20, 80)
        citation_rows.append(
            {
                "citation_id": _id("citation", idx, j),
                "trace_id": trace_id,
                "chunk_id": chunk_rows[chunk_rank]["chunk_id"],
                "project_id": project_id,
                "response_span_start": cursor,
                "response_span_end": cursor + span_len,
                "timestamp": when,
            }
        )
        cursor += span_len + rng.randint(10, 40)

    return trace, retrieval, chunk_rows, citation_rows


def seed_clickhouse(project_id: UUID) -> dict[str, int]:
    """Generate the demo telemetry dataset. Idempotent: wipes prior
    rows for this project_id, then re-inserts."""
    _clear_clickhouse_for_project(project_id)
    client = get_client()
    # Two independent RNG streams: one for content (citation count,
    # scores, models, etc.), one for timestamps. Decoupling them means
    # tuning the content distribution can't accidentally shift which
    # traces land in the dashboard's default 7d window - a real
    # gotcha in earlier iterations.
    content_rng = random.Random(RNG_SEED)
    time_rng = random.Random(RNG_SEED + 1)

    end = _now()
    start = end - timedelta(days=DAYS_SPAN)
    span_seconds = (end - start).total_seconds()

    traces: list[dict[str, object]] = []
    retrievals: list[dict[str, object]] = []
    chunks: list[dict[str, object]] = []
    citations: list[dict[str, object]] = []

    def _when() -> datetime:
        # Bias timestamps toward the recent end of the window. Exponent
        # 1.6 puts the mean trace ~11 days into an 18-day window and
        # roughly half the dataset in the last 7 days, so the default
        # dashboard view shows a representative sample of the quality
        # signal. Reads as growing-usage telemetry rather than uniform
        # synthetic noise.
        t = 1 - time_rng.random() ** 1.6
        return start + timedelta(seconds=t * span_seconds)

    # Plain traces (indices 0..NUM_PLAIN_TRACES-1), then RAG (offset by
    # NUM_PLAIN_TRACES). Distinct index ranges keep deterministic IDs
    # stable even if the split changes later.
    for i in range(NUM_PLAIN_TRACES):
        traces.append(_make_plain_trace(content_rng, i, project_id, _when()))

    for j in range(NUM_RAG_TRACES):
        idx = NUM_PLAIN_TRACES + j
        trace, retrieval, chunk_rows, citation_rows = _make_rag_flow(
            content_rng, idx, project_id, _when()
        )
        traces.append(trace)
        retrievals.append(retrieval)
        chunks.extend(chunk_rows)
        citations.extend(citation_rows)

    _insert(client, "traces", traces)
    _insert(client, "retrievals", retrievals)
    _insert(client, "retrieved_chunks", chunks)
    _insert(client, "citations", citations)

    return {
        "traces": len(traces),
        "retrievals": len(retrievals),
        "retrieved_chunks": len(chunks),
        "citations": len(citations),
    }


def _insert(client, table: str, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    data = [[row[col] for col in columns] for row in rows]
    client.insert(table, data, column_names=columns)


async def main() -> int:
    print("Seeding Postgres...")
    project_id, raw_key = await seed_postgres()
    print(f"  project_id = {project_id}")

    print("Seeding ClickHouse...")
    counts = seed_clickhouse(project_id)
    for table, n in counts.items():
        print(f"  {table}: {n} rows")

    await engine.dispose()

    print()
    print("=" * 64)
    print("Demo API key (save this, it will not be shown again):")
    print(f"  {raw_key}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
