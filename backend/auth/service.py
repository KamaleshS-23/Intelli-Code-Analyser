"""
Email/password auth plus history storage.
Passwords are hashed with PBKDF2; sessions are random tokens.
"""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId

from db.mongo import require_db


PBKDF2_ITERATIONS = 120_000


def _utc_now():
    return datetime.now(timezone.utc)


def hash_password(password: str, salt: Optional[str] = None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return salt, digest


def verify_password(password: str, salt: str, expected: str) -> bool:
    _, digest = hash_password(password, salt)
    return hmac.compare_digest(digest, expected)


def _serialize_user(doc):
    return {
        "id": str(doc["_id"]),
        "email": doc["email"],
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
    }


def register_user(email: str, password: str):
    email = email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError("Enter a valid email address.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    db = require_db()
    if db.users.find_one({"email": email}):
        raise ValueError("An account with this email already exists.")

    salt, digest = hash_password(password)
    result = db.users.insert_one(
        {
            "email": email,
            "password_salt": salt,
            "password_hash": digest,
            "created_at": _utc_now(),
        }
    )
    user = db.users.find_one({"_id": result.inserted_id})
    return create_session(user, event="register")


def login_user(email: str, password: str):
    email = email.strip().lower()
    db = require_db()
    user = db.users.find_one({"email": email})
    if not user or not verify_password(password, user["password_salt"], user["password_hash"]):
        raise ValueError("Invalid email or password.")
    return create_session(user, event="login")


def create_session(user, event="login"):
    db = require_db()
    token = secrets.token_urlsafe(32)
    db.sessions.insert_one(
        {
            "token": token,
            "user_id": user["_id"],
            "created_at": _utc_now(),
        }
    )
    db.login_history.insert_one(
        {
            "user_id": user["_id"],
            "email": user["email"],
            "event": event,
            "created_at": _utc_now(),
        }
    )
    return {"token": token, "user": _serialize_user(user)}


def get_user_by_token(token: Optional[str]):
    if not token:
        return None
    db = require_db()
    session = db.sessions.find_one({"token": token})
    if not session:
        return None
    user = db.users.find_one({"_id": session["user_id"]})
    return user


def logout_user(token: Optional[str]):
    if not token:
        return
    db = require_db()
    db.sessions.delete_one({"token": token})


def save_scan_history(user, scan_result: dict, source: str):
    db = require_db()
    debt = scan_result.get("debt_report") or {}
    issues = debt.get("issues") or []
    suggestions = [
        {
            "rule": issue.get("rule"),
            "class_name": issue.get("class_name"),
            "method_name": issue.get("method_name"),
            "line_number": issue.get("line_number"),
            "severity": issue.get("severity"),
            "message": issue.get("message"),
            "suggestion": issue.get("suggestion"),
        }
        for issue in issues
        if issue.get("suggestion")
    ]
    db.scan_history.insert_one(
        {
            "user_id": user["_id"],
            "email": user.get("email"),
            "source": source,
            "project_name": scan_result.get("project_name"),
            "project_path": scan_result.get("project_path"),
            "debt_score": debt.get("total_score", 0),
            "issue_count": len(issues),
            "scan_time_seconds": (scan_result.get("statistics") or {}).get("scan_time_seconds", 0),
            "severity_counts": debt.get("severity_counts") or {},
            "rule_counts": debt.get("rule_counts") or {},
            "suggestions": suggestions,
            "created_at": _utc_now(),
        }
    )


def list_login_history(user, limit=30):
    db = require_db()
    rows = db.login_history.find({"user_id": user["_id"]}).sort("created_at", -1).limit(limit)
    return [
        {
            "event": row.get("event"),
            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        }
        for row in rows
    ]


def list_scan_history(user, limit=20):
    db = require_db()
    rows = db.scan_history.find({"user_id": user["_id"]}).sort("created_at", -1).limit(limit)
    history = []
    for row in rows:
        history.append(
            {
                "id": str(row["_id"]),
                "project_name": row.get("project_name"),
                "source": row.get("source"),
                "debt_score": row.get("debt_score", 0),
                "issue_count": row.get("issue_count", 0),
                "scan_time_seconds": row.get("scan_time_seconds", 0),
                "severity_counts": row.get("severity_counts") or {},
                "suggestions": row.get("suggestions") or [],
                "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
            }
        )
    return history


def get_scan_history_item(user, item_id: str):
    db = require_db()
    try:
        oid = ObjectId(item_id)
    except InvalidId:
        return None
    row = db.scan_history.find_one({"_id": oid, "user_id": user["_id"]})
    if not row:
        return None
    return {
        "id": str(row["_id"]),
        "project_name": row.get("project_name"),
        "source": row.get("source"),
        "debt_score": row.get("debt_score", 0),
        "issue_count": row.get("issue_count", 0),
        "suggestions": row.get("suggestions") or [],
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
    }
