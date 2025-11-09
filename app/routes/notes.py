# app/routes/notes.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from bson import ObjectId
from flask import Blueprint, jsonify, request, g

from ..db import get_db
from ..utils import error_response, resolve_existing_id
from ..auth import require_auth  # uses g.current_user set by token

notes_bp = Blueprint("notes", __name__, url_prefix="/api/v1/notes")
notes_bp.strict_slashes = False

# -------- helpers --------

def _iso(dt):
    if not dt:
        return None
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt)

def _serialize_note(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Make Mongo doc JSON-safe for responses."""
    return {
        "id": str(doc.get("_id")),
        "match_id": str(doc.get("match_id")) if doc.get("match_id") else None,
        "note": doc.get("note", ""),
        "created_by": {
            "user_id": str(doc.get("created_by", {}).get("user_id", "")),
            "username": doc.get("created_by", {}).get("username"),
            "role": doc.get("created_by", {}).get("role", "user"),
        },
        "created_at": _iso(doc.get("created_at")),
        "edited_at": _iso(doc.get("edited_at")),
    }

def _object_id(id_str: str):
    try:
        return ObjectId(id_str)
    except Exception:
        return None

# -------- routes --------

@notes_bp.post("/")
@require_auth()
def create_note():
    db = get_db()
    data = request.get_json(silent=True) or {}

    match_id = (data.get("match_id") or "").strip()
    text = (data.get("note") or "").strip()

    if not match_id or not text:
        return error_response("VALIDATION_ERROR", "match_id and note are required", 422)

    # returns the canonical _id (ObjectId OR string) if it exists; otherwise None
    mid = resolve_existing_id(db, "matches", match_id)
    if not mid:
        return error_response("NOT_FOUND", "Match not found", 404)

    doc = {
        "match_id": mid,                 # store in the same type as matches._id
        "note": text,
        "created_by": {
            "user_id": str(g.current_user["_id"]),
            "username": g.current_user.get("email"),
            "role": g.current_user.get("role", "user"),
        },
        "created_at": datetime.now(timezone.utc),
        "edited_at": None,
    }
    ins = db.match_notes.insert_one(doc)
    saved = db.match_notes.find_one({"_id": ins.inserted_id})
    return jsonify(_serialize_note(saved)), 201



@notes_bp.get("/")
@require_auth()
def list_notes():
    db = get_db()
    match_id = (request.args.get("match_id") or "").strip()
    if not match_id:
        return error_response("VALIDATION_ERROR", "match_id is required", 422)

    mid = resolve_existing_id(db, "matches", match_id)
    if not mid:
        return error_response("NOT_FOUND", "Match not found", 404)

    cur = db.match_notes.find({"match_id": mid}).sort([("created_at", 1)])
    return jsonify([_serialize_note(d) for d in cur]), 200


@notes_bp.put("/<note_id>")
@require_auth()
def update_note(note_id: str):
    """Owner (or admin) can edit note text."""
    db = get_db()
    nid = _object_id(note_id)
    if not nid:
        return error_response("VALIDATION_ERROR", "note_id must be a valid ObjectId", 422)

    data = request.get_json(silent=True) or {}
    text = (data.get("note") or "").strip()
    if not text:
        return error_response("VALIDATION_ERROR", "note text is required", 422)

    note = db.match_notes.find_one({"_id": nid})
    if not note:
        return error_response("NOT_FOUND", "Note not found", 404)

    is_owner = str(note.get("created_by", {}).get("user_id")) == str(g.current_user["_id"])
    is_admin = g.current_user.get("role") == "admin"
    if not (is_owner or is_admin):
        return error_response("UNAUTHORISED", "You cannot edit this note", 403)

    db.match_notes.update_one(
        {"_id": nid},
        {"$set": {"note": text, "edited_at": datetime.now(timezone.utc)}}
    )
    updated = db.match_notes.find_one({"_id": nid})
    return jsonify(_serialize_note(updated)), 200


@notes_bp.delete("/<note_id>")
@require_auth()
def delete_note(note_id: str):
    """Owner (or admin) can delete note."""
    db = get_db()
    nid = _object_id(note_id)
    if not nid:
        return error_response("VALIDATION_ERROR", "note_id must be a valid ObjectId", 422)

    note = db.match_notes.find_one({"_id": nid})
    if not note:
        return error_response("NOT_FOUND", "Note not found", 404)

    is_owner = str(note.get("created_by", {}).get("user_id")) == str(g.current_user["_id"])
    is_admin = g.current_user.get("role") == "admin"
    if not (is_owner or is_admin):
        return error_response("UNAUTHORISED", "You cannot delete this note", 403)

    db.match_notes.delete_one({"_id": nid})
    return jsonify({"deleted": True}), 200
