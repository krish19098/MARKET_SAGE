"""Single-user authentication (personal use): argon2 password hash + optional TOTP, JWT in an httpOnly cookie."""

from __future__ import annotations

from datetime import timedelta

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request, status

from market_sage.core.config import Settings, get_settings
from market_sage.core.timeutil import utcnow

COOKIE = "ms_session"
_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_login(settings: Settings, username: str, password: str, totp: str | None) -> bool:
    if settings.auth_password_hash is None:
        return False
    if username != settings.auth_username:
        return False
    try:
        _ph.verify(settings.auth_password_hash.get_secret_value(), password)
    except (VerificationError, InvalidHashError):
        return False
    if settings.auth_totp_secret is not None:
        if not totp or not pyotp.TOTP(settings.auth_totp_secret.get_secret_value()).verify(totp, valid_window=1):
            return False
    return True


def issue_token(settings: Settings) -> str:
    now = utcnow()
    return jwt.encode({"sub": settings.auth_username, "iat": now, "exp": now + timedelta(minutes=settings.jwt_ttl_minutes)},
                      settings.jwt_secret.get_secret_value(), algorithm="HS256")


def require_user(request: Request) -> str:
    settings: Settings = getattr(request.app.state, "settings", None) or get_settings()
    token = request.cookies.get(COOKIE)
    if not token:
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() or None
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    try:
        data = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid session") from exc
    return str(data["sub"])
