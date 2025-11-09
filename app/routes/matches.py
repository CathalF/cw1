from ..utils import resolve_existing_id

# app/matches.py
from datetime import datetime
from bson import ObjectId
from flask import Blueprint, request, jsonify
from ..db import get_db
from ..decorators import require_auth
from ..utils import normalize_id, normalize_many, error_response, ok_list
from ..pagination import parse_pagination_args
# --- 1. IMPORT THE SCHEMA ---
from ..validators import MatchSchema 

matches_bp = Blueprint("matches", __name__, url_prefix="/api/v1/matches")


# ---------- Helpers ----------

def _parse_iso_date(s: str | None):
    if not s: return None
    try: return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception: return None


def _serialize_match(doc):
    """Convert ObjectIds and datetime fields to JSON-safe types"""
    if not doc: return None
    
    # --- USE NORMALIZE_ID ---
    doc = normalize_id(doc) 
    
    # Normalize other string IDs (if they are present)
    for key in ["competition_id", "season_id", "home_team_id", "away_team_id"]:
        if key in doc and isinstance(doc[key], ObjectId):
            doc[key] = str(doc[key])
    
    if "date" in doc and isinstance(doc["date"], datetime):
        doc["date"] = doc["date"].isoformat()
    return doc


# ---------- Routes ----------

@matches_bp.get("/")
def list_matches():
    db = get_db()
    page, page_size = parse_pagination_args(request, default=20, max_=100)
    q = {}
    comp = request.args.get("competition_id")
    season = request.args.get("season_id")
    status = request.args.get("status")
    date_from = _parse_iso_date(request.args.get("from"))
    date_to = _parse_iso_date(request.args.get("to"))
    team_id = request.args.get("team_id")

    # --- FIX: Use string IDs for queries ---
    if comp:
        q["competition_id"] = comp
    if season:
        q["season_id"] = season
    if status:
        q["status"] = status
    if date_from or date_to:
        q["date"] = {}
        if date_from: q["date"]["$gte"] = date_from
        if date_to: q["date"]["$lte"] = date_to
    if team_id:
        q["$or"] = [{"home_team_id": team_id}, {"away_team_id": team_id}]

    cursor = (
        db.matches.find(q)
        .sort("date", 1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_serialize_match(doc) for doc in cursor]
    total = db.matches.count_documents(q)
    return ok_list(items, page, page_size, total)


from datetime import datetime, date as dt_date
from ..utils import resolve_existing_id

@matches_bp.post("/")
@require_auth(role="admin")
def create_match():
    db = get_db()
    payload = request.get_json(force=True) or {}
    data = MatchSchema().load(payload)  # returns date as datetime.date

    # Resolve incoming identifiers to actual _ids in your DB
    comp_id   = resolve_existing_id(db, "competitions", data["competition_id"])
    season_id = resolve_existing_id(db, "seasons",      data["season_id"])
    home_id   = resolve_existing_id(db, "teams",        data["home_team_id"])
    away_id   = resolve_existing_id(db, "teams",        data["away_team_id"])

    if not comp_id:   return error_response("VALIDATION_ERROR", "Competition not found", 422)
    if not season_id: return error_response("VALIDATION_ERROR", "Season not found", 422)
    if not home_id:   return error_response("VALIDATION_ERROR", "Home team not found", 422)
    if not away_id:   return error_response("VALIDATION_ERROR", "Away team not found", 422)

    data["competition_id"] = comp_id
    data["season_id"]      = season_id
    data["home_team_id"]   = home_id
    data["away_team_id"]   = away_id

    # Ensure Mongo gets a datetime (not a date)
    if isinstance(data.get("date"), dt_date) and not isinstance(data["date"], datetime):
        data["date"] = datetime.combine(data["date"], datetime.min.time())

    res = db.matches.insert_one(data)
    doc = db.matches.find_one({"_id": res.inserted_id})
    return jsonify(_serialize_match(doc)), 201


@matches_bp.put("/<match_id>")
@require_auth(role="admin")
def update_match(match_id):
    db = get_db()
    payload = request.get_json(force=True) or {}
    
    # --- 2. VALIDATE THE DATA ---
    data = MatchSchema(partial=True).load(payload)

    # --- 3. CHECK FOREIGN KEYS (if provided) ---
    if "competition_id" in data and not db.competitions.find_one({"_id": data["competition_id"]}):
        return error_response("VALIDATION_ERROR", "Competition not found", 422)
    if "season_id" in data and not db.seasons.find_one({"_id": data["season_id"]}):
        return error_response("VALIDATION_ERROR", "Season not found", 422)
    if "home_team_id" in data and not db.teams.find_one({"_id": data["home_team_id"]}):
        return error_response("VALIDATION_ERROR", "Home team not found", 422)
    if "away_team_id" in data and not db.teams.find_one({"_id": data["away_team_id"]}):
        return error_response("VALIDATION_ERROR", "Away team not found", 422)

    res = db.matches.update_one({"_id": match_id}, {"$set": data})
    if res.matched_count == 0:
        # --- FIX: Added 3 arguments ---
        return error_response("NOT_FOUND", "Match not found", 404)

    doc = db.matches.find_one({"_id": match_id})
    return jsonify(_serialize_match(doc)), 200


@matches_bp.delete("/<match_id>")
@require_auth(role="admin")
def delete_match(match_id):
    db = get_db()
    # --- FIX: Use string ID ---
    res = db.matches.delete_one({"_id": match_id})
    if res.deleted_count == 0:
        # --- FIX: Added 3 arguments ---
        return error_response("NOT_FOUND", "Match not found", 404)
    return "", 204