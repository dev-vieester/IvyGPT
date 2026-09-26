from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ivy_gpt.config import settings
from ivy_gpt.db.crud import (
    create_user,
    get_user_by_email,
    revoke_refresh_token,
    upsert_google_user
)
from ivy_gpt.db.models import User
from ivy_gpt.db.session import get_db
from ivy_gpt.schemas.auth import (
    AuthMessageResponse,
    AuthTokenResponse,
    EmailRequest,
    LogoutRequest,
    OTPVerifyRequest,
    RefreshTokenRequest,
    SignupCompleteRequest,
    SignupOTPVerifiedResponse,
    UserResponse
)
from ivy_gpt.services.auth import (
    create_jwt,
    decode_jwt,
    create_signup_token,
    decode_signup_token,
    get_current_user,
    hash_value,
    issue_auth_tokens,
    refresh_auth_tokens,
    send_email_otp,
    verify_email_otp
)


router = APIRouter(prefix="/auth", tags=["auth"])
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def auth_response(user: User, access_token: str, refresh_token: str) -> AuthTokenResponse:
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user)
    )


@router.post("/signup/email/start", response_model=AuthMessageResponse)
async def start_email_signup(
    payload: EmailRequest,
    db: AsyncSession = Depends(get_db)
) -> AuthMessageResponse:
    existing_user = await get_user_by_email(db, payload.email)

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account already exists for this email."
        )

    await send_email_otp(payload.email, "signup")

    return AuthMessageResponse(
        success=True,
        message="Verification code sent to your email."
    )


@router.post("/signup/email/verify", response_model=SignupOTPVerifiedResponse)
async def verify_email_signup(payload: OTPVerifyRequest) -> SignupOTPVerifiedResponse:
    valid = await verify_email_otp(payload.email, payload.otp, "signup")

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code."
        )

    return SignupOTPVerifiedResponse(
        signup_token=create_signup_token(payload.email),
        message="Email verified. Complete your profile."
    )


@router.post("/signup/email/complete", response_model=AuthTokenResponse)
async def complete_email_signup(
    payload: SignupCompleteRequest,
    db: AsyncSession = Depends(get_db)
) -> AuthTokenResponse:
    email = decode_signup_token(payload.signup_token)
    existing_user = await get_user_by_email(db, email)

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account already exists for this email."
        )

    user = await create_user(
        db=db,
        email=email,
        name=payload.name,
        age=payload.age,
        provider="email"
    )
    access_token, refresh_token = await issue_auth_tokens(db, user)

    return auth_response(user, access_token, refresh_token)


@router.post("/login/email/start", response_model=AuthMessageResponse)
async def start_email_login(
    payload: EmailRequest,
    db: AsyncSession = Depends(get_db)
) -> AuthMessageResponse:
    user = await get_user_by_email(db, payload.email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account exists for this email."
        )

    await send_email_otp(payload.email, "login")

    return AuthMessageResponse(
        success=True,
        message="Login code sent to your email."
    )


@router.post("/login/email/verify", response_model=AuthTokenResponse)
async def verify_email_login(
    payload: OTPVerifyRequest,
    db: AsyncSession = Depends(get_db)
) -> AuthTokenResponse:
    valid = await verify_email_otp(payload.email, payload.otp, "login")

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired login code."
        )

    user = await get_user_by_email(db, payload.email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account exists for this email."
        )

    access_token, refresh_token = await issue_auth_tokens(db, user)
    return auth_response(user, access_token, refresh_token)


@router.get("/google/start")
async def start_google_login():
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured."
        )

    redirect_uri = f"{settings.app_base_url.rstrip('/')}/auth/google/callback"
    state = create_jwt(
        subject="google-oauth",
        token_type="oauth_state",
        expires_delta=timedelta(minutes=10)
    )
    query = urlencode({
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account"
    })

    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{query}")


@router.get("/google/callback")
async def google_callback(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured."
        )

    code = request.query_params.get("code")
    state_token = request.query_params.get("state")

    if not code or not state_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Google OAuth callback parameters."
        )

    decode_jwt(state_token, "oauth_state")

    redirect_uri = f"{settings.app_base_url.rstrip('/')}/auth/google/callback"

    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }
        )

        if token_response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google token exchange failed."
            )

        token = token_response.json()
        access_token_from_google = token.get("access_token")

        if not access_token_from_google:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google did not return an access token."
            )

        userinfo_response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token_from_google}"}
        )

        if userinfo_response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not fetch Google account information."
            )

        userinfo = userinfo_response.json()

    email = userinfo.get("email")
    google_sub = userinfo.get("sub")

    if not email or not google_sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google did not return required account information."
        )

    user = await upsert_google_user(
        db=db,
        email=email,
        name=userinfo.get("name"),
        google_sub=google_sub
    )
    access_token, refresh_token = await issue_auth_tokens(db, user)

    redirect_url = (
        f"/?auth_access_token={access_token}"
        f"&auth_refresh_token={refresh_token}"
    )
    return RedirectResponse(redirect_url)


@router.post("/refresh", response_model=AuthTokenResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
) -> AuthTokenResponse:
    user, access_token, refresh_token = await refresh_auth_tokens(db, payload.refresh_token)
    return auth_response(user, access_token, refresh_token)


@router.post("/logout", response_model=AuthMessageResponse)
async def logout(
    payload: LogoutRequest,
    db: AsyncSession = Depends(get_db)
) -> AuthMessageResponse:
    await revoke_refresh_token(db, hash_value(payload.refresh_token))
    return AuthMessageResponse(success=True, message="Signed out.")


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
