import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, Request

from app.database import supabase

JWT_SECRET = os.getenv("MOBILE_AUTH_JWT_SECRET", os.getenv("SUPABASE_KEY", "bizness-mobile-dev-secret"))
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_MINUTES = int(os.getenv("MOBILE_ACCESS_TOKEN_TTL_MINUTES", "2880"))
REFRESH_TOKEN_TTL_DAYS = int(os.getenv("MOBILE_REFRESH_TOKEN_TTL_DAYS", "30"))


def _create_token(
    *,
    sme_id: str,
    email: str,
    token_type: str,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sme_id,
        "email": email,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_mobile_access_token(*, sme_id: str, email: str) -> str:
    return _create_token(
        sme_id=sme_id,
        email=email,
        token_type="access",
        expires_delta=timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES),
    )


def create_mobile_refresh_token(*, sme_id: str, email: str) -> str:
    return _create_token(
        sme_id=sme_id,
        email=email,
        token_type="refresh",
        expires_delta=timedelta(days=REFRESH_TOKEN_TTL_DAYS),
    )


def decode_mobile_token(token: str, *, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as error:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.") from error
    except jwt.PyJWTError as error:
        raise HTTPException(status_code=401, detail="Invalid mobile session token.") from error

    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail="Invalid token type.")

    return payload


def get_user_by_sme_id(sme_id: str) -> dict[str, Any]:
    res = supabase.table("sme").select("*").eq("sme_id", sme_id).execute()
    if len(res.data) == 0:
        raise HTTPException(status_code=401, detail="User session invalid or expired.")
    return res.data[0]


def get_current_user(request: Request) -> dict[str, Any]:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        payload = decode_mobile_token(token, expected_type="access")
        return get_user_by_sme_id(str(payload["sub"]))

    sme_id = request.cookies.get("bizness_session")
    if sme_id:
        return get_user_by_sme_id(sme_id)

    raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")
