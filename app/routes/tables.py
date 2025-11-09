from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime
import re
from typing import Any, Dict, Deque

from bson import Regex
from flask import Blueprint, jsonify, request

from ..db import get_db, collection
from ..utils import error_response, maybe_object_id

tables_bp = Blueprint("tables", __name__, url_prefix="/api/v1/tables")
MATCHES = collection("matches")

# ---------- helpers ----------

def _iso(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date().isoformat()
    except Exception:
        return None

_score_pat = re.compile(r"^\s*(\d+)\D+(\d+)\s*$")

def _parse_ft(score: Any):
    """
    Accepts any of:
      - {'ft': [2,1]}  (your JSON)
      - {'ft': {'home': 2, 'away': 1}}  (newer code sometimes)
      - '2-1' (string fallback)
    Returns (home, away) or None.
    """
    if isinstance(score, dict):
        ft = score.get("ft")
        if isinstance(ft, list) and len(ft) == 2:
            try: return int(ft[0]), int(ft[1])
            except Exception: return None
        if isinstance(ft, dict):
            try: return int(ft.get("home", 0)), int(ft.get("away", 0))
            except Exception: return None
    if isinstance(score, str):
        m = _score_pat.match(score)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None

def _ensure_row(table: Dict[str, Dict], team: str):
    if team not in table:
        table[team] = {
            "team": team,
            "played": 0, "wins": 0, "draws": 0, "losses": 0,
            "gf": 0, "ga": 0, "gd": 0, "points": 0,
        }

def _tally_row(row: Dict, gf: int, ga: int, pts_win=3, pts_draw=1, pts_loss=0):
    row["played"] += 1
    row["gf"] += gf
    row["ga"] += ga
    if gf > ga:
        row["wins"] += 1; row["points"] += pts_win; res = "W"
    elif gf < ga:
        row["losses"] += 1; row["points"] += pts_loss; res = "L"
    else:
        row["draws"] += 1; row["points"] += pts_draw; res = "D"
    row["gd"] = row["gf"] - row["ga"]
    return res

def _sort_key(row):
    # points desc, gd desc, gf desc, name asc
    return (-row["points"], -row["gd"], -row["gf"], row["team"])

def _slim(r: dict):
    return {
        "played": r["played"], "wins": r["wins"], "draws": r["draws"], "losses": r["losses"],
        "gf": r["gf"], "ga": r["ga"], "gd": r["gd"], "points": r["points"],
    }

@tables_bp.get("/<competition_id>/<season_id>")
def league_table_by_ids(competition_id: str, season_id: str):
    db = get_db()
    if not competition_id or not season_id:
        return error_response("VALIDATION_ERROR", "competition_id and season_id are required", 422)

    comp_id = maybe_object_id(competition_id) or competition_id
    seas_id = maybe_object_id(season_id) or season_id

    status = (request.args.get("status") or "").strip()
    match_filter = {"competition_id": comp_id, "season_id": seas_id}
    if status:
        match_filter["status"] = status

    # Helpers that return NULL when score is missing/unparseable (so we can filter them out)
    ft_home_expr = {
        "$let": { "vars": { "ft": "$score.ft", "s": "$score" }, "in":
            { "$switch": {
                "branches": [
                    # ft as array [h,a]
                    { "case": { "$eq": [ { "$type": "$$ft" }, "array" ] },
                      "then": {
                        "$let": { "vars": {
                          "h": { "$arrayElemAt": [ "$$ft", 0 ] },
                          "a": { "$arrayElemAt": [ "$$ft", 1 ] }
                        }, "in":
                          { "$cond": [
                            { "$and": [ { "$isNumber": "$$h" }, { "$isNumber": "$$a" } ] },
                            { "$toInt": "$$h" },
                            None
                          ] }
                        }
                      } },
                    # ft as object {home, away}
                    { "case": { "$eq": [ { "$type": "$$ft" }, "object" ] },
                      "then": {
                        "$let": { "vars": { "h": "$score.ft.home", "a": "$score.ft.away" }, "in":
                          { "$cond": [
                            { "$and": [ { "$isNumber": "$$h" }, { "$isNumber": "$$a" } ] },
                            { "$toInt": "$$h" },
                            None
                          ] }
                        }
                      } },
                    # score as string "h-a"
                    { "case": { "$eq": [ { "$type": "$$s.score" }, "string" ] },
                      "then": {
                        "$let": { "vars": {
                          "m": { "$regexFind": { "input": "$$s.score", "regex": r"^\s*(\d+)\D+(\d+)\s*$" } }
                        }, "in":
                          { "$cond": [
                            { "$ifNull": [ "$$m", False ] },
                            { "$toInt": { "$arrayElemAt": [ "$$m.captures", 0 ] } },
                            None
                          ] }
                        }
                      } }
                ],
                "default": None
            } }
        }
    }

    ft_away_expr = {
        "$let": { "vars": { "ft": "$score.ft", "s": "$score" }, "in":
            { "$switch": {
                "branches": [
                    # ft as array [h,a]
                    { "case": { "$eq": [ { "$type": "$$ft" }, "array" ] },
                      "then": {
                        "$let": { "vars": {
                          "h": { "$arrayElemAt": [ "$$ft", 0 ] },
                          "a": { "$arrayElemAt": [ "$$ft", 1 ] }
                        }, "in":
                          { "$cond": [
                            { "$and": [ { "$isNumber": "$$h" }, { "$isNumber": "$$a" } ] },
                            { "$toInt": "$$a" },
                            None
                          ] }
                        }
                      } },
                    # ft as object {home, away}
                    { "case": { "$eq": [ { "$type": "$$ft" }, "object" ] },
                      "then": {
                        "$let": { "vars": { "h": "$score.ft.home", "a": "$score.ft.away" }, "in":
                          { "$cond": [
                            { "$and": [ { "$isNumber": "$$h" }, { "$isNumber": "$$a" } ] },
                            { "$toInt": "$$a" },
                            None
                          ] }
                        }
                      } },
                    # score as string "h-a"
                    { "case": { "$eq": [ { "$type": "$$s.score" }, "string" ] },
                      "then": {
                        "$let": { "vars": {
                          "m": { "$regexFind": { "input": "$$s.score", "regex": r"^\s*(\d+)\D+(\d+)\s*$" } }
                        }, "in":
                          { "$cond": [
                            { "$ifNull": [ "$$m", False ] },
                            { "$toInt": { "$arrayElemAt": [ "$$m.captures", 1 ] } },
                            None
                          ] }
                        }
                      } }
                ],
                "default": None
            } }
        }
    }

    pipeline = [
        { "$match": match_filter },

        { "$project": {
            "home_row": { "team_id": "$home_team_id", "gf": ft_home_expr, "ga": ft_away_expr },
            "away_row": { "team_id": "$away_team_id", "gf": ft_away_expr, "ga": ft_home_expr }
        }},
        { "$project": { "rows": ["$home_row", "$away_row"] } },
        { "$unwind": "$rows" },

        # ⛔ Exclude unplayed/unknown scores (gf or ga is null)
        { "$match": { "rows.gf": { "$ne": None }, "rows.ga": { "$ne": None } } },

        { "$addFields": {
            "rows.res": {
                "$switch": {
                    "branches": [
                        { "case": { "$gt": ["$rows.gf", "$rows.ga"] }, "then": "W" },
                        { "case": { "$lt": ["$rows.gf", "$rows.ga"] }, "then": "L" }
                    ],
                    "default": "D"
                }
            }
        }},

        { "$group": {
            "_id": "$rows.team_id",
            "played": { "$sum": 1 },
            "wins":   { "$sum": { "$cond": [ { "$eq": ["$rows.res","W"] }, 1, 0 ] } },
            "draws":  { "$sum": { "$cond": [ { "$eq": ["$rows.res","D"] }, 1, 0 ] } },
            "losses": { "$sum": { "$cond": [ { "$eq": ["$rows.res","L"] }, 1, 0 ] } },
            "gf":     { "$sum": "$rows.gf" },
            "ga":     { "$sum": "$rows.ga" }
        }},

        { "$addFields": {
            "gd": { "$subtract": ["$gf", "$ga"] },
            "points": { "$add": [ { "$multiply": ["$wins", 3] }, { "$multiply": ["$draws", 1] } ] }
        }},

        { "$sort": { "points": -1, "gd": -1, "gf": -1, "_id": 1 } },

        { "$lookup": { "from": "teams", "localField": "_id", "foreignField": "_id", "as": "team" } },
        { "$unwind": { "path": "$team", "preserveNullAndEmptyArrays": True } },

        { "$project": {
            "_id": 0,
            "team_id": { "$toString": "$_id" },
            "team_name": "$team.name",
            "played": 1, "wins": 1, "draws": 1, "losses": 1,
            "gf": 1, "ga": 1, "gd": 1, "points": 1
        }},
    ]

    table = list(db.matches.aggregate(pipeline))
    return jsonify({
        "competition_id": str(comp_id),
        "season_id": str(seas_id),
        "status": status or None,
        "table": table
    }), 200