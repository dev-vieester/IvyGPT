from pydantic import BaseModel, EmailStr, Field


class EmailRequest(BaseModel):
    email: EmailStr


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6)


class SignupCompleteRequest(BaseModel):
    signup_token: str
    name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=13, le=120)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class AuthMessageResponse(BaseModel):
    success: bool
    message: str


class SignupOTPVerifiedResponse(BaseModel):
    signup_token: str
    message: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None = None
    age: int | None = None
    provider: str

    model_config = {"from_attributes": True}


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
