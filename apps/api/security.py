import secrets

from fastapi import Header, HTTPException, status

from config import settings


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = f"Bearer {settings.api_secret_key}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing token")
