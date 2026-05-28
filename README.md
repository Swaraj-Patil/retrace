# Retrace

**RAG-native observability for LLM applications.**

Most tracing tools log the LLM call well but treat retrieval as a black box: you see the final prompt but not which chunks were retrieved, what their scores were, or how the embedding model performed. Retrace surfaces every chunk that fed every answer, scores retrieval quality, links citations back to source chunks, and flags answers that drift from retrieved context.

> **Status:** Pre-alpha. Active development. Not production-ready.

## Architecture

- **API:** FastAPI ingestion service (Python 3.12+)
- **Traces store:** ClickHouse (high-cardinality event data)
- **Metadata store:** Postgres (orgs, projects, users, API keys)
- **SDKs:** Python first; TypeScript later
- **Frontend:** Next.js 14 + Tailwind + shadcn/ui + Tremor

## Repository layout

```
retrace/
├── apps/
│   ├── api/             # FastAPI ingestion service
│   └── web/             # Next.js dashboard
├── packages/
│   ├── sdk-python/      # Python SDK
│   └── shared/          # Shared schemas
├── infra/
│   └── docker/          # Docker configs
├── .github/workflows/   # CI
└── docker-compose.yml   # Local dev stack
```

## Quickstart

Requires Python 3.12+, Node 20+, Docker, `uv`, and `pnpm`.

```bash
# 1. Clone and enter
git clone https://github.com/<your-handle>/retrace
cd retrace

# 2. Install dependencies
pnpm install
uv sync

# 3. Start local services
docker compose up -d

# 4. Verify
curl http://localhost:8123/ping  # ClickHouse
pg_isready -h localhost -U retrace  # Postgres
```

API and web app come online in Days 3-6 (see project plan).

## Development plan

- **Day 1 (done):** Repo scaffold, Docker Compose, CI skeleton
- **Day 2:** Postgres + ClickHouse schemas, seed data
- **Day 3:** FastAPI ingestion service
- **Day 4-5:** Python SDK with OpenAI and Anthropic auto-instrumentation; RAG instrumentation API
- **Day 6:** Next.js dashboard skeleton
- **Day 7:** End-to-end demo

## License

MIT. See [LICENSE](./LICENSE).
