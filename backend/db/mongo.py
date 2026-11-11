"""
MongoDB connection for auth, login history, and saved scan suggestions.
"""

import os
from functools import lru_cache

from pymongo import MongoClient
from pymongo.errors import PyMongoError


DEFAULT_URI = "mongodb://127.0.0.1:27017"
DEFAULT_DB = "tech_debt_agent"


@lru_cache(maxsize=1)
def get_client():
    uri = os.getenv("MONGODB_URI", DEFAULT_URI)
    return MongoClient(uri, serverSelectionTimeoutMS=4000)


def get_db():
    name = os.getenv("MONGODB_DB", DEFAULT_DB)
    return get_client()[name]


def ping():
    get_client().admin.command("ping")


def ensure_indexes():
    db = get_db()
    db.users.create_index("email", unique=True)
    db.sessions.create_index("token", unique=True)
    db.sessions.create_index("user_id")
    db.login_history.create_index([("user_id", 1), ("created_at", -1)])
    db.scan_history.create_index([("user_id", 1), ("created_at", -1)])


def require_db():
    try:
        ping()
        ensure_indexes()
        return get_db()
    except PyMongoError as exc:
        raise RuntimeError(
            "MongoDB is not reachable. Start MongoDB locally or set MONGODB_URI. "
            f"Details: {exc}"
        ) from exc
