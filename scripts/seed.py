"""Seed local dev databases with a demo org, project, API key, and 10 traces.

Idempotent: rerunning wipes the demo org (and its cascade) plus all ClickHouse
trace rows tagged with the demo project_id, then re-inserts fresh data.

Usage:
    uv run python scripts/seed.py
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_DNS, UUID, uuid4, uuid5

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

PLAIN_MODELS = ["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet-20241022"]
EMBED_MODELS = ["text-embedding-3-small", "voyage-3"]

SAMPLE_QUERIES = [
    "How do I configure retries in the SDK?",
    "What does retrieval_score below 0.4 mean?",
    "Show me the steps to enable citations.",
    "Where is the dashboard hosted?",
    "How do I rotate an API key?",
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
]


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


def _make_plain_trace(project_id: UUID, when: datetime) -> dict[str, object]:
    model = random.choice(PLAIN_MODELS)
    tokens_in = random.randint(120, 1200)
    tokens_out = random.randint(50, 600)
    latency_ms = random.randint(400, 3500)
    return {
        "trace_id": uuid4(),
        "span_id": uuid4(),
        "parent_span_id": None,
        "project_id": project_id,
        "start_time": when,
        "end_time": when + timedelta(milliseconds=latency_ms),
        "latency_ms": latency_ms,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "status": "OK",
        "attributes": json.dumps({"kind": "llm.chat", "vendor": model.split("-")[0]}),
    }


def seed_clickhouse(project_id: UUID) -> dict[str, int]:
    """Insert 10 traces (5 plain LLM, 5 RAG). Return per-table insert counts."""
    _clear_clickhouse_for_project(project_id)
    client = get_client()

    traces: list[dict[str, object]] = []
    retrievals: list[dict[str, object]] = []
    chunks: list[dict[str, object]] = []
    citations: list[dict[str, object]] = []

    base = _now() - timedelta(hours=6)
    rng = random.Random(42)

    # 5 plain LLM calls
    for i in range(5):
        when = base + timedelta(minutes=i * 7)
        traces.append(_make_plain_trace(project_id, when))

    # 5 RAG flows: trace + retrieval + N chunks + 1-2 citations
    for i in range(5):
        when = base + timedelta(minutes=40 + i * 9)
        trace = _make_plain_trace(project_id, when)
        # Override a few fields so it reads as a RAG flow.
        attrs = json.loads(trace["attributes"])  # type: ignore[arg-type]
        attrs["kind"] = "rag.qa"
        trace["attributes"] = json.dumps(attrs)
        trace["tokens_in"] = rng.randint(800, 2400)  # bigger prompt with context
        traces.append(trace)

        retrieval_id = uuid4()
        top_k = rng.choice([3, 4, 5])
        retrieval_latency = rng.randint(80, 350)
        retrievals.append(
            {
                "retrieval_id": retrieval_id,
                "trace_id": trace["trace_id"],
                "span_id": uuid4(),
                "project_id": project_id,
                "query": SAMPLE_QUERIES[i],
                "embedding_model": rng.choice(EMBED_MODELS),
                "top_k": top_k,
                "latency_ms": retrieval_latency,
                "timestamp": when,
            }
        )

        chunk_ids: list[UUID] = []
        for rank in range(top_k):
            cid = uuid4()
            chunk_ids.append(cid)
            chunks.append(
                {
                    "chunk_id": cid,
                    "retrieval_id": retrieval_id,
                    "project_id": project_id,
                    "rank": rank,
                    "similarity_score": round(rng.uniform(0.35, 0.92) - rank * 0.05, 4),
                    "content": rng.choice(SAMPLE_CHUNKS),
                    "source_doc_id": f"doc_{rng.randint(100, 999)}",
                    "doc_metadata": json.dumps(
                        {"title": f"Docs page {rng.randint(1, 50)}", "url": "https://docs.retrace.dev"}
                    ),
                    "timestamp": when,
                }
            )

        # 1-2 citations pointing at the top-ranked chunks
        num_citations = rng.choice([1, 2])
        cursor = 0
        for j in range(num_citations):
            span_len = rng.randint(20, 80)
            citations.append(
                {
                    "citation_id": uuid4(),
                    "trace_id": trace["trace_id"],
                    "chunk_id": chunk_ids[j],
                    "project_id": project_id,
                    "response_span_start": cursor,
                    "response_span_end": cursor + span_len,
                    "timestamp": when,
                }
            )
            cursor += span_len + 10

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
