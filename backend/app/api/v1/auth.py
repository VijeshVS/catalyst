from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose.exceptions import JWTError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_db
from app.core.security import (
    create_token_pair,
    decode_token,
    ensure_auth_attempt_allowed,
    hash_password,
    record_auth_attempt,
    unauthorized,
    verify_password,
)
from app.models.models import User
from app.schemas.schemas import (
    AuthResponse,
    RefreshTokenRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


def _auth_response(user: User) -> AuthResponse:
    access_token, refresh_token = create_token_pair(user.id)
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await ensure_auth_attempt_allowed(request)
    await record_auth_attempt(request)

    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc

    await db.refresh(user)
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(
    data: UserLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await ensure_auth_attempt_allowed(request)
    await record_auth_attempt(request)

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(data.password, user.hashed_password):
        raise unauthorized("Incorrect email or password")

    return _auth_response(user)


@router.post("/refresh", response_model=AuthResponse)
async def refresh_tokens(
    data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = decode_token(data.refresh_token, expected_type="refresh")
    except JWTError as exc:
        raise unauthorized("Invalid or expired refresh token") from exc

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if user is None:
        raise unauthorized("User account no longer exists")

    return _auth_response(user)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)
