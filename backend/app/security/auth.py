from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.database import get_db
from app.db.models.user import User

security_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(
    data: dict[str, Any],
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta
        if expires_delta
        else timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(UTC)})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any] | None:
    """Decode and validate a JWT access token."""
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except (jwt.PyJWTError, Exception):
        return None


def get_current_user(
    auth: Annotated[HTTPAuthorizationCredentials | None, Security(security_scheme)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Extract and validate the current authenticated user from Bearer header."""
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(auth.credentials, settings)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload["sub"]
    user = db.get(User, user_id)
    if user is None or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(
    auth: Annotated[HTTPAuthorizationCredentials | None, Security(security_scheme)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User | None:
    """Extract current user if authenticated; otherwise returns None without raising 401."""
    if not auth or not auth.credentials:
        return None
    payload = decode_access_token(auth.credentials, settings)
    if not payload or "sub" not in payload:
        return None
    user = db.get(User, payload["sub"])
    return user if user and user.active else None


def require_role(*allowed_roles: str):
    """Enforce server-side role check."""
    def role_checker(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied for role '{current_user.role}'. Required: {', '.join(allowed_roles)}",
            )
        return current_user
    return role_checker


DEFAULT_ACCOUNTS = [
    {
        "name": "Investigator Dave",
        "email": "investigator@forensecure.local",
        "password": "Investigator@123",
        "role": "investigator",
    },
    {
        "name": "Authorized Officer Alice",
        "email": "officer1@forensecure.local",
        "password": "Officer@123",
        "role": "authorized_officer",
    },
    {
        "name": "Authorized Officer Bob",
        "email": "officer2@forensecure.local",
        "password": "Officer@123",
        "role": "authorized_officer",
    },
    {
        "name": "Admin Superuser",
        "email": "admin@forensecure.local",
        "password": "Admin@123",
        "role": "admin",
    },
]


def seed_default_users(db: Session) -> None:
    """Ensure standard demonstrator accounts exist in database."""
    for account in DEFAULT_ACCOUNTS:
        existing = db.scalar(select(User).where(User.email == account["email"]))
        if not existing:
            user = User(
                name=account["name"],
                email=account["email"],
                password_hash=hash_password(account["password"]),
                role=account["role"],
                active=True,
            )
            db.add(user)
    db.commit()
