from __future__ import annotations

from functools import wraps
from typing import Optional, Literal, Callable

import jwt
from flask import request, g

from .config import config
from .db import get_db, collection
from .utils import error_response


def _extract_token_from_headers() -> str | None:
    """
    Prefer 'Authorization: Bearer <token>' but also accept 'x-access-token'.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return request.headers.get("x-access-token")


def require_auth(role: Optional[Literal["user", "admin"]] = None) -> Callable:
    """
    Decorator for protected routes.
      @require_auth()          -> any logged-in user
      @require_auth("admin")   -> admin only
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            token = _extract_token_from_headers()
            if not token:
                return error_response("UNAUTHENTICATED", "Authentication required", 401)

            # Make sure the token hasn't been explicitly revoked first.
            db = get_db()
            if db.blacklist.find_one({"token": token}):
                return error_response("TOKEN_REVOKED", "Token has been revoked", 401)

            # Decode the JWT so we can read the user information.
            try:
                payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                return error_response("TOKEN_EXPIRED", "Token has expired", 401)
            except jwt.InvalidTokenError:
                return error_response("INVALID_TOKEN", "Invalid authentication token", 401)

            sub = str(payload.get("sub", "")).strip()
            if not sub:
                return error_response("INVALID_TOKEN", "Invalid token payload", 401)

            # User identifiers are stored as string UUIDs in the collection.
            users = collection("users")
            user = users.find_one({"_id": sub})
            if not user:
                return error_response("UNAUTHENTICATED", "User no longer exists", 401)

            if role == "admin" and user.get("role") != "admin":
                return error_response("UNAUTHORISED", "Admin privileges required", 403)

            # Stash the authenticated user on the request context for later handlers.
            g.current_user = {
                "_id": str(user["_id"]),
                "email": user.get("email"),
                "role": user.get("role", "user"),
            }
            g.token_payload = payload

            return fn(*args, **kwargs)
        return wrapper
    return decorator
