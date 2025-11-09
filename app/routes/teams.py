# app/teams.py
from flask import Blueprint, request, jsonify

from ..db import get_db
from ..decorators import require_auth
from ..utils import (
    normalize_id,
    normalize_many,
    error_response,
    ok_list,
    maybe_object_id,
)
from ..pagination import parse_pagination_args
from ..validators import TeamCreateSchema, TeamUpdateSchema

teams_bp = Blueprint("teams", __name__, url_prefix="/api/v1/teams")

@teams_bp.get("/")
def list_teams():
    db = get_db()
    page, page_size = parse_pagination_args(request, default=20, max_=100)
    q = {}
    name = request.args.get("name")
    country = request.args.get("country")
    if name:
        q["$text"] = {"$search": name}
    if country:
        q["country"] = country
    cursor = (db.teams.find(q)
                    .sort("name", 1)
                    .skip((page - 1) * page_size)
                    .limit(page_size))
    items = normalize_many(list(cursor))
    total = db.teams.count_documents(q)
    return ok_list(items, page, page_size, total)

@teams_bp.get("/<team_id>")
def get_team(team_id):
    db = get_db()
    if not team_id:
        return error_response("VALIDATION_ERROR", "Invalid team id", 400)

    key = maybe_object_id(team_id)
    doc = db.teams.find_one({"_id": key})
    if not doc:
        # --- FIX: Added 3 arguments ---
        return error_response("NOT_FOUND", "Team not found", 404)
    return jsonify(normalize_id(doc)), 200

@teams_bp.post("/")
@require_auth(role="admin")
def create_team():
    db = get_db()
    payload = request.get_json(force=True) or {}
    data = TeamCreateSchema().load(payload)
    try:
        res = db.teams.insert_one(data)
    except Exception as e:
        # --- FIX: Added 3 arguments ---
        return error_response("SERVER_ERROR", f"Insert failed: {e}", 400)
    doc = db.teams.find_one({"_id": res.inserted_id})
    return jsonify(normalize_id(doc)), 201

@teams_bp.put("/<team_id>")
@require_auth(role="admin")
def update_team(team_id):
    db = get_db()
    payload = request.get_json(force=True) or {}
    data = TeamUpdateSchema().load(payload)
    if not team_id:
        return error_response("VALIDATION_ERROR", "Invalid team id", 400)

    key = maybe_object_id(team_id)
    res = db.teams.update_one({"_id": key}, {"$set": data})
    if res.matched_count == 0:
        # --- FIX: Added 3 arguments ---
        return error_response("NOT_FOUND", "Team not found", 404)
    doc = db.teams.find_one({"_id": key})
    return jsonify(normalize_id(doc)), 200

@teams_bp.delete("/<team_id>")
@require_auth(role="admin")
def delete_team(team_id):
    db = get_db()
    if not team_id:
        return error_response("VALIDATION_ERROR", "Invalid team id", 400)

    key = maybe_object_id(team_id)
    res = db.teams.delete_one({"_id": key})
    if res.deleted_count == 0:
        # --- FIX: Added 3 arguments ---
        return error_response("NOT_FOUND", "Team not found", 404)
    return "", 204
