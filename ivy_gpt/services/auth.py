import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ivy_gpt.config import settings
from ivy_gpt.db.crud import create_refresh_token, get_refresh_token, get_user_by_id
from ivy_gpt.db.models import User
from ivy_gpt.db.session import get_db
from ivy_gpt.services.email_tasks import send_otp_email


security = HTTPBearer(auto_error=False)
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_otp(email: str, otp: str, purpose: str) -> str:
    payload = f"{purpose}:{normalize_email(email)}:{otp}".encode("utf-8")
    secret = settings.jwt_secret_key.encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def otp_key(email: str, purpose: str) -> str:
    return f"auth:otp:{purpose}:{normalize_email(email)}"


async def send_email_otp(email: str, purpose: Literal["signup", "login"]) -> None:
    otp = f"{secrets.randbelow(1_000_000):06d}"
    key = otp_key(email, purpose)

    await redis_client.setex(
        key,
        settings.otp_expire_minutes * 60,
        hash_otp(email, otp, purpose)
    )

    send_otp_email.delay(normalize_email(email), otp)


async def verify_email_otp(email: str, otp: str, purpose: Literal["signup", "login"]) -> bool:
    key = otp_key(email, purpose)
    stored_hash = await redis_client.get(key)

    if not stored_hash:
        return False

    valid = hmac.compare_digest(stored_hash, hash_otp(email, otp, purpose))

    if valid:
        await redis_client.delete(key)

    return valid


def create_jwt(subject: str, token_type: str, expires_delta: timedelta, extra: dict | None = None) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "typ": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": secrets.token_urlsafe(24)
    }

    if extra:
        payload.update(extra)

    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def decode_jwt(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token."
        ) from exc

    if payload.get("typ") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type."
        )

    return payload


async def issue_auth_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    access_token = create_jwt(
        subject=user.id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
    )
    refresh_token = create_jwt(
        subject=user.id,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days)
    )
    refresh_payload = decode_jwt(refresh_token, "refresh")

    await create_refresh_token(
        db=db,
        user_id=user.id,
        token_hash=hash_value(refresh_token),
        expires_at=datetime.fromtimestamp(refresh_payload["exp"], UTC).replace(tzinfo=None)
    )

    return access_token, refresh_token


def create_signup_token(email: str) -> str:
    return create_jwt(
        subject=normalize_email(email),
        token_type="signup",
        expires_delta=timedelta(minutes=15)
    )


def decode_signup_token(token: str) -> str:
    payload = decode_jwt(token, "signup")
    return normalize_email(payload["sub"])


async def refresh_auth_tokens(db: AsyncSession, refresh_token: str) -> tuple[User, str, str]:
    payload = decode_jwt(refresh_token, "refresh")
    token_hash = hash_value(refresh_token)
    stored_token = await get_refresh_token(db, token_hash)

    if not stored_token or stored_token.revoked or stored_token.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid."
        )

    user = await get_user_by_id(db, payload["sub"])

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive or missing."
        )

    stored_token.revoked = True
    await db.commit()

    access_token, new_refresh_token = await issue_auth_tokens(db, user)
    return user, access_token, new_refresh_token


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required."
        )

    payload = decode_jwt(credentials.credentials, "access")
    user = await get_user_by_id(db, payload["sub"])

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive or missing."
        )

    return user
