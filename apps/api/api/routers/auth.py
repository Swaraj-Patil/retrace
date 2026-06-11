"""User-session auth endpoints: register, login, logout, me.

All four endpoints exchange an opaque session token (``rts_…``) via
``Authorization: Bearer …``. Register also logs the user in (returns
the same shape as login) so onboarding is register-and-go, not
register-then-login.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies.auth import (
    Unauthorized,
    UserActor,
    get_current_user,
    get_db,
)
from api.models import Membership, Org, User
from api.schemas.auth import (
    LoginRequest,
    MeResponse,
    OrgRef,
    RegisterRequest,
    SessionTokenResponse,
)
from api.services.auth import (
    authenticate_user,
    issue_session,
    register_user,
    revoke_session,
)
from api.services.auth_rate_limit import check_login_rate_limit

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionTokenResponse,
)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionTokenResponse:
    result = await register_user(
        db,
        email=body.email,
        password=body.password,
        name=body.name,
    )
    return SessionTokenResponse(
        token=result.session.raw_token,
        expires_at=result.session.expires_at,
    )


@router.post("/login", response_model=SessionTokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionTokenResponse:
    # Rate limit fires *before* the argon2 verify so a brute-force
    # attacker is throttled without the server paying the hash cost on
    # every attempt.
    client_ip = request.client.host if request.client else "unknown"
    check_login_rate_limit(client_ip=client_ip, email=body.email)

    user = await authenticate_user(db, email=body.email, password=body.password)
    if user is None:
        # Uniform with the bearer-auth 401 — unknown email, wrong
        # password, and "user has no password set" all collapse here.
        raise Unauthorized

    session = await issue_session(db, user_id=user.id)
    return SessionTokenResponse(token=session.raw_token, expires_at=session.expires_at)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    actor: Annotated[UserActor, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await revoke_session(db, session_id=actor.session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeResponse)
async def me(
    actor: Annotated[UserActor, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MeResponse:
    user = (
        await db.execute(select(User).where(User.id == actor.user_id))
    ).scalar_one()

    org_rows = (
        await db.execute(
            select(Org, Membership.role)
            .join(Membership, Membership.org_id == Org.id)
            .where(Membership.user_id == actor.user_id)
            .order_by(Org.created_at)
        )
    ).all()

    return MeResponse(
        user_id=user.id,
        email=user.email,
        name=user.name,
        orgs=[
            OrgRef(id=org.id, name=org.name, slug=org.slug, role=role.value)
            for org, role in org_rows
        ],
    )
