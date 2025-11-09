# app/auth.py
from __future__ import annotations

import uuid
from typing import Any
from datetime import datetime, timezone

import jwt
from flask import Blueprint, g, jsonify, request

from werkzeug.security import generate_password_hash, check_password_hash

from .config import config
from .db import collection, get_db
from .utils import error_response
from .decorators import require_auth

# Use a clear URL prefix so routes mount under /api/v1/auth/...
auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


# ------------ helpers ------------
def hash_password(password: str) -> str:
    # PBKDF2 (sha256 + random salt)
    return generate_password_hash(str(password), method="pbkdf2:sha256", salt_length=16)

def verify_password(password: str, password_hash: str) -> bool:
    return check_password_hash(password_hash or "", str(password))

def create_token(user: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["_id"]),                     # subject = user id (string UUID)
        "role": user.get("role", "user"),
        "iat": int(now.timestamp()),
        "exp": int((now + config.JWT_EXPIRATION).timestamp()),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


# ------------ routes ------------
@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password")

    if not email or not password:
        return error_response("VALIDATION_ERROR", "Email and password are required", 422)

    users = collection("users")
    if users.find_one({"email": email}, {"_id": 1}):
        return error_response("DUPLICATE", "Email already registered", 409)

    user_id = str(uuid.uuid4())
    doc = {
        "_id": user_id,                       # string UUID
        "email": email,
        "password_hash": hash_password(password),
        "role": "user",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    users.insert_one(doc)

    token = create_token(doc)
    return jsonify({
        "token": token,
        "user": {"_id": user_id, "email": email, "role": "user"}
    }), 201


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password")

    if not email or not password:
        return error_response("VALIDATION_ERROR", "Email and password are required", 422)

    users = collection("users")
    user = users.find_one({"email": email})
    if not user or not verify_password(password, user.get("password_hash", "")):
        return error_response("UNAUTHENTICATED", "Invalid email or password", 401)

    token = create_token(user)
    return jsonify({
        "token": token,
        "user": {"_id": str(user["_id"]), "email": user["email"], "role": user.get("role", "user")}
    }), 200


@auth_bp.post("/logout")
@require_auth()  # any logged-in user can log out
def logout():
    """
    Blacklist the exact token string so it can't be reused.
    Accepts either `Authorization: Bearer <token>` or `x-access-token: <token>`.
    """
    db = get_db()

    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = request.headers.get("x-access-token")

    if not token:
        return error_response("UNAUTHENTICATED", "Authentication required", 401)

    db.blacklist.insert_one({
        "token": token,
        "blacklisted_at": datetime.now(timezone.utc),
        "user_id": str(g.current_user.get("_id"))
    })
    return jsonify({"message": "Logout successful"}), 200
