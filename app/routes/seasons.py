# app/seasons.py
from bson import ObjectId
from flask import Blueprint, request, jsonify

from ..db import get_db
from ..decorators import require_auth
from ..utils import (
    normalize_id,
    normalize_many,
    error_response,
    ok_list,
    maybe_object_id,
    resolve_existing_id,
)
from ..pagination import parse_pagination_args
from ..validators import SeasonSchema

seasons_bp = Blueprint("seasons", __name__, url_prefix="/api/v1/seasons")

@seasons_bp.get("/")
def list_seasons():
    db = get_db()
    page, page_size = parse_pagination_args(request, default=20, max_=100)
    q = {}
    competition_id = request.args.get("competition_id")
    status = request.args.get("status")
    if competition_id:
        resolved = resolve_existing_id(db, "competitions", competition_id)
        if not resolved:
            return error_response("VALIDATION_ERROR", "Invalid competition_id", 400)
        q["competition_id"] = resolved
    if status:
        q["status"] = status
    cursor = (db.seasons.find(q)
                        .sort("start_date", -1)
                        .skip((page - 1) * page_size)
                        .limit(page_size))
    items = normalize_many(list(cursor))
    total = db.seasons.count_documents(q)
    return ok_list(items, page, page_size, total)

@seasons_bp.get("/<season_id>")
def get_season(season_id):
    db = get_db()
    if not season_id:
        return error_response("VALIDATION_ERROR", "Invalid season id", 400)

    key = maybe_object_id(season_id)
    doc = db.seasons.find_one({"_id": key})
    if not doc:
        # --- FIX: Added 3 arguments ---
        return error_response("NOT_FOUND", "Season not found", 404)
    doc = normalize_id(doc)
    if isinstance(doc.get("competition_id"), ObjectId):
        doc["competition_id"] = str(doc["competition_id"])
    return jsonify(doc), 200

@seasons_bp.post("/")
@require_auth(role="admin")
def create_season():
    db = get_db()
    payload = request.get_json(force=True) or {}
    data = SeasonSchema().load(payload)

    resolved_comp = resolve_existing_id(db, "competitions", data["competition_id"])
    if not resolved_comp:
        return error_response("VALIDATION_ERROR", "Competition not found", 422)

    data["competition_id"] = resolved_comp

    res = db.seasons.insert_one(data)
    doc = db.seasons.find_one({"_id": res.inserted_id})

    # 🔧 convert ObjectIds to strings for JSON
    doc = normalize_id(doc)
    if isinstance(doc.get("competition_id"), ObjectId):
        doc["competition_id"] = str(doc["competition_id"])

    return jsonify(doc), 201

@seasons_bp.put("/<season_id>")
@require_auth(role="admin")
def update_season(season_id):
    db = get_db()
    payload = request.get_json(force=True) or {}
    data = SeasonSchema(partial=True).load(payload)
    if not season_id:
        return error_response("VALIDATION_ERROR", "Invalid season id", 400)

    key = maybe_object_id(season_id)
    if "competition_id" in data:
        resolved_comp = resolve_existing_id(db, "competitions", data["competition_id"])
        if not resolved_comp:
            return error_response("VALIDATION_ERROR", "Invalid competition_id", 422)
        data["competition_id"] = resolved_comp
    res = db.seasons.update_one({"_id": key}, {"$set": data})
    if res.matched_count == 0:
        # --- FIX: Added 3 arguments ---
        return error_response("NOT_FOUND", "Season not found", 404)
    doc = db.seasons.find_one({"_id": key})
    doc = normalize_id(doc)
    if isinstance(doc.get("competition_id"), ObjectId):
        doc["competition_id"] = str(doc["competition_id"])
    return jsonify(doc), 200

@seasons_bp.delete("/<season_id>")
@require_auth(role="admin")
def delete_season(season_id):
    db = get_db()
    if not season_id:
        return error_response("VALIDATION_ERROR", "Invalid season id", 400)

    key = maybe_object_id(season_id)
    res = db.seasons.delete_one({"_id": key})
    if res.deleted_count == 0:
        # --- FIX: Added 3 arguments ---
        return error_response("NOT_FOUND", "Season not found", 404)
    return "", 204
