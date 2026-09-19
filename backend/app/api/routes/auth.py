from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.blockchain.ledger import append_block
from app.core.config import Settings, get_settings
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.auth import (
    LoginRequest,
    SignupRequest,
    SupabaseSyncRequest,
    TokenResponse,
    UserResponse,
)
from app.security.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(
    req: SignupRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    existing = db.scalar(select(User).where(User.email == req.email.strip().lower()))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{req.email}' already exists.",
        )

    valid_roles = {"investigator", "authorized_officer", "admin"}
    role = req.role if req.role in valid_roles else "investigator"

    user = User(
        name=req.name.strip(),
        email=req.email.strip().lower(),
        password_hash=hash_password(req.password),
        role=role,
        active=True,
    )
    db.add(user)
    db.flush()

    append_block(
        db=db,
        action="user_registered",
        file_id=None,
        file_hash="0" * 64,
        audit_data={"user_id": user.id, "email": user.email, "role": user.role},
        actor_id=user.id,
    )
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role}, settings)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
def login(
    credentials: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == credentials.email.strip().lower()))
    if user is None or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password. Please check your credentials.",
        )
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated.",
        )

    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role}, settings)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post("/supabase-sync", response_model=TokenResponse)
def supabase_sync(
    req: SupabaseSyncRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Synchronize an authenticated Supabase user into the local database for foreign keys."""
    email = req.email.strip().lower()
    user = db.scalar(select(User).where((User.email == email) | (User.id == req.supabase_id)))

    valid_roles = {"investigator", "authorized_officer", "admin"}
    role = req.role if req.role in valid_roles else "investigator"

    if user is None:
        user = User(
            id=req.supabase_id,
            name=req.name.strip() or email.split("@")[0],
            email=email,
            password_hash=hash_password(str(uuid4())),  # Managed by Supabase
            role=role,
            active=True,
        )
        db.add(user)
        db.flush()
        append_block(
            db=db,
            action="supabase_user_synced",
            file_id=None,
            file_hash="0" * 64,
            audit_data={"user_id": user.id, "email": user.email, "role": user.role},
            actor_id=user.id,
        )
        db.commit()
        db.refresh(user)
    else:
        # Update name/role if provided
        if req.name and req.name.strip():
            user.name = req.name.strip()
        if req.role in valid_roles:
            user.role = role
        db.commit()
        db.refresh(user)

    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role}, settings)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post("/logout")
def logout() -> dict[str, str]:
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/config")
def get_auth_config(settings: Settings = Depends(get_settings)) -> dict[str, str | bool]:
    """Returns the configured Supabase client settings from .env without exposing secrets."""
    url = settings.supabase_url.strip() if settings.supabase_url else ""
    if url.endswith("/rest/v1/"):
        url = url[:-9]
    elif url.endswith("/rest/v1"):
        url = url[:-8]
    url = url.rstrip("/")

    has_supabase = bool(url and settings.supabase_anon_key.strip())
    return {
        "supabase_url": url,
        "supabase_anon_key": settings.supabase_anon_key.strip() if settings.supabase_anon_key else "",
        "supabase_enabled": has_supabase,
    }


