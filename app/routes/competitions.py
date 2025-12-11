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
from ..validators import CompetitionSchema

competitions_bp = Blueprint("competitions", __name__, url_prefix="/api/v1/competitions")

@competitions_bp.get("/")
def list_competitions():
    db = get_db()
    page, page_size = parse_pagination_args(request, default=20, max_=100)
    q = {}
    country = request.args.get("country")
    if country:
        # Country filters allow clients to slice the competition list quickly.
        q["country"] = country
    cursor = (db.competitions.find(q)
                           .sort([("tier", 1), ("name", 1)])
                           .skip((page - 1) * page_size)
                           .limit(page_size))
    items = normalize_many(list(cursor))
    total = db.competitions.count_documents(q)
    return ok_list(items, page, page_size, total)

@competitions_bp.get("/<comp_id>")
def get_competition(comp_id):
    db = get_db()
    if not comp_id:
        return error_response("VALIDATION_ERROR", "Invalid competition id", 400)

    key = maybe_object_id(comp_id)
    doc = db.competitions.find_one({"_id": key})
    if not doc:
        return error_response("NOT_FOUND", "Competition not found", 404)
    return jsonify(normalize_id(doc)), 200

@competitions_bp.post("/")
@require_auth(role="admin")
def create_competition():
    db = get_db()
    payload = request.get_json(force=True) or {}
    data = CompetitionSchema().load(payload)
    res = db.competitions.insert_one(data)
    doc = db.competitions.find_one({"_id": res.inserted_id})
    return jsonify(normalize_id(doc)), 201

@competitions_bp.put("/<comp_id>")
@require_auth(role="admin")
def update_competition(comp_id):
    db = get_db()
    payload = request.get_json(force=True) or {}
    data = CompetitionSchema(partial=True).load(payload)
    if not comp_id:
        return error_response("VALIDATION_ERROR", "Invalid competition id", 400)

    key = maybe_object_id(comp_id)
    res = db.competitions.update_one({"_id": key}, {"$set": data})
    if res.matched_count == 0:
        return error_response("NOT_FOUND", "Competition not found", 404)
    doc = db.competitions.find_one({"_id": key})
    return jsonify(normalize_id(doc)), 200

@competitions_bp.delete("/<comp_id>")
@require_auth(role="admin")
def delete_competition(comp_id):
    db = get_db()
    if not comp_id:
        return error_response("VALIDATION_ERROR", "Invalid competition id", 400)

    key = maybe_object_id(comp_id)
    res = db.competitions.delete_one({"_id": key})
    if res.deleted_count == 0:
        return error_response("NOT_FOUND", "Competition not found", 404)
    return "", 204
