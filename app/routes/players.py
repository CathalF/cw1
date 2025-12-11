from flask import Blueprint, request, jsonify

from ..db import get_db
from ..decorators import require_auth
from ..utils import (
    normalize_id,
    normalize_many,
    error_response,
    ok_list,
    resolve_existing_id,
    maybe_object_id,
)
from ..pagination import parse_pagination_args
from ..validators import PlayerSchema

players_bp = Blueprint("players", __name__, url_prefix="/api/v1/players")

@players_bp.get("/")
def list_players():
    db = get_db()
    page, page_size = parse_pagination_args(request, default=20, max_=100)
    q = {}
    name = request.args.get("name")
    team_id = request.args.get("team_id")
    if name:
        q["$text"] = {"$search": name}
    if team_id:
        # Let callers supply any known team identifier and resolve it to the primary key.
        resolved = resolve_existing_id(db, "teams", team_id)
        if not resolved:
            return error_response("VALIDATION_ERROR", "Invalid team_id", 400)
        q["current_team_id"] = resolved
    cursor = (db.players.find(q)
                      .sort("name", 1)
                      .skip((page - 1) * page_size)
                      .limit(page_size))
    items = normalize_many(list(cursor))
    total = db.players.count_documents(q)
    return ok_list(items, page, page_size, total)

@players_bp.get("/<player_id>")
def get_player(player_id):
    db = get_db()
    if not player_id:
        return error_response("VALIDATION_ERROR", "Invalid player id", 400)

    key = maybe_object_id(player_id)
    doc = db.players.find_one({"_id": key})
    if not doc:
        return error_response("NOT_FOUND", "Player not found", 404)
    return jsonify(normalize_id(doc)), 200

@players_bp.post("/")
@require_auth(role="admin")
def create_player():
    db = get_db()
    payload = request.get_json(force=True) or {}
    data = PlayerSchema().load(payload)
    res = db.players.insert_one(data)
    doc = db.players.find_one({"_id": res.inserted_id})
    return jsonify(normalize_id(doc)), 201

@players_bp.put("/<player_id>")
@require_auth(role="admin")
def update_player(player_id):
    db = get_db()
    payload = request.get_json(force=True) or {}
    data = PlayerSchema(partial=True).load(payload)
    if not player_id:
        return error_response("VALIDATION_ERROR", "Invalid player id", 400)

    key = maybe_object_id(player_id)
    res = db.players.update_one({"_id": key}, {"$set": data})
    if res.matched_count == 0:
        return error_response("NOT_FOUND", "Player not found", 404)
    doc = db.players.find_one({"_id": key})
    return jsonify(normalize_id(doc)), 200

@players_bp.delete("/<player_id>")
@require_auth(role="admin")
def delete_player(player_id):
    db = get_db()
    if not player_id:
        return error_response("VALIDATION_ERROR", "Invalid player id", 400)

    key = maybe_object_id(player_id)
    res = db.players.delete_one({"_id": key})
    if res.deleted_count == 0:
        return error_response("NOT_FOUND", "Player not found", 404)
    return "", 204
