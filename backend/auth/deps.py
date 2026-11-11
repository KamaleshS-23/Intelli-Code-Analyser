from typing import Optional

from fastapi import Header, HTTPException

from auth.service import get_user_by_token


def extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return authorization.strip()


def require_user(authorization: Optional[str] = Header(default=None)):
    token = extract_token(authorization)
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in first.")
    return user


def optional_user(authorization: Optional[str] = Header(default=None)):
    token = extract_token(authorization)
    try:
        return get_user_by_token(token)
    except RuntimeError:
        return None
