from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    role: str
    active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "investigator"


class SupabaseSyncRequest(BaseModel):
    supabase_id: str
    name: str
    email: str
    role: str = "investigator"
