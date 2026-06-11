"""End-to-end integration test for the session / api-key / read loop.

A fresh user registers via ``/v1/auth/register``, mints an API key
through the console, ingests a trace with that key, then reads the
trace back via the session on all three read endpoints (list, detail,
metrics). This is the same loop the smoke matrix walked manually
during Commit 3 - here it's a permanent regression: the console-minted
key and the user session land on the same project's data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import delete, select

from api.clickhouse.client import get_client
from api.db.session import SessionLocal
from api.models import Membership, Org, User


async def _drop_user(email: str, project_id: UUID | None = None) -> None:
    """Delete the user + cascade their org. Also wipe any rows we
    ingested into ClickHouse so reruns don't accumulate."""
    async with SessionLocal() as session:
        user_id = (
            await session.execute(select(User.id).where(User.email == email))
        ).scalar_one_or_none()
        if user_id is not None:
            org_ids = (
                await session.execute(
                    select(Membership.org_id).where(Membership.user_id == user_id)
                )
            ).scalars().all()
            for org_id in org_ids:
                await session.execute(delete(Org).where(Org.id == org_id))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
    if project_id is not None:
        ch = get_client()
        ch.command(
            "ALTER TABLE traces DELETE WHERE project_id = %(pid)s",
            parameters={"pid": str(project_id)},
            settings={"mutations_sync": 2},
        )


async def test_register_console_key_ingest_session_read_roundtrip(
    client: AsyncClient,
) -> None:
    email = f"integration-{uuid4().hex}@retrace.test"
    project_id: UUID | None = None
    try:
        # 1. Register -> token (auto-login by Change 1).
        reg = await client.post(
            "/v1/auth/register",
            json={"email": email, "password": "integration-pw-1234", "name": "Int"},
        )
        assert reg.status_code == 201, reg.text
        session_token = reg.json()["token"]
        sess_auth = {"Authorization": f"Bearer {session_token}"}

        # 2. List projects -> default project_id.
        listed = await client.get("/v1/console/projects", headers=sess_auth)
        assert listed.status_code == 200
        projects = listed.json()["projects"]
        assert len(projects) == 1
        project_id = UUID(projects[0]["id"])
        assert projects[0]["slug"] == "default"

        # 3. Mint an API key via the console.
        keyed = await client.post(
            f"/v1/console/projects/{project_id}/keys",
            json={"name": "integration-key"},
            headers=sess_auth,
        )
        assert keyed.status_code == 201
        raw_key = keyed.json()["raw_key"]
        assert raw_key.startswith("rt_")

        # 4. Ingest one trace with the raw key.
        trace_id = uuid4()
        span_id = uuid4()
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        payload = {
            "traces": [
                {
                    "trace_id": str(trace_id),
                    "span_id": str(span_id),
                    "start_time": now,
                    "end_time": now,
                    "latency_ms": 100,
                    "model": "gpt-4o",
                    "tokens_in": 10,
                    "tokens_out": 5,
                    "status": "OK",
                    "attributes": {"kind": "integration"},
                }
            ],
            "retrievals": [],
            "chunks": [],
            "citations": [],
        }
        ingest = await client.post(
            "/v1/ingest",
            json=payload,
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert ingest.status_code == 200, ingest.text
        assert ingest.json()["inserted"]["traces"] == 1
        assert UUID(ingest.json()["project_id"]) == project_id

        # 5a. /v1/traces via session+project_id sees the ingested row.
        traces = await client.get(
            f"/v1/traces?project_id={project_id}&limit=10", headers=sess_auth
        )
        assert traces.status_code == 200
        body = traces.json()
        assert body["total"] == 1
        assert len(body["traces"]) == 1
        assert UUID(body["traces"][0]["trace_id"]) == trace_id

        # 5b. /v1/traces/{id} via session+project_id returns the detail.
        detail = await client.get(
            f"/v1/traces/{trace_id}?project_id={project_id}", headers=sess_auth
        )
        assert detail.status_code == 200
        assert UUID(detail.json()["trace"]["trace_id"]) == trace_id
        assert detail.json()["trace"]["model"] == "gpt-4o"

        # 5c. /v1/metrics/overview via session+project_id counts it.
        metrics = await client.get(
            f"/v1/metrics/overview?project_id={project_id}", headers=sess_auth
        )
        assert metrics.status_code == 200
        assert metrics.json()["total_traces"] == 1
        assert metrics.json()["rag_traces"] == 0
    finally:
        await _drop_user(email, project_id)
