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

# ---------- NEW-SCHEMA route (IDs in the URL) ----------

@tables_bp.get("/<competition_id>/<season_id>")
def league_table_by_ids(competition_id: str, season_id: str):
    """
    New schema:
      competition_id, season_id (ObjectId)
      home_team_id, away_team_id (ObjectId)
      status: "finished"
      score.ft.{home, away}, score.winner
    """
    db = get_db()
    if not competition_id or not season_id:
        return error_response("VALIDATION_ERROR", "competition_id and season_id are required", 422)

    comp_id = maybe_object_id(competition_id)
    seas_id = maybe_object_id(season_id)

    pipeline = [
        {"$match": {"competition_id": comp_id, "season_id": seas_id, "status": "finished"}},
        {"$project": {
            "home_row": {
                "team_id": "$home_team_id",
                "gf": {"$ifNull": ["$score.ft.home", 0]},
                "ga": {"$ifNull": ["$score.ft.away", 0]},
                "res": {
                    "$switch": {
                        "branches": [
                            {"case": {"$eq": ["$score.winner","home"]}, "then": "W"},
                            {"case": {"$eq": ["$score.winner","draw"]}, "then": "D"},
                            {"case": {"$eq": ["$score.winner","away"]}, "then": "L"},
                        ],
                        "default": "D"
                    }
                }
            },
            "away_row": {
                "team_id": "$away_team_id",
                "gf": {"$ifNull": ["$score.ft.away", 0]},
                "ga": {"$ifNull": ["$score.ft.home", 0]},
                "res": {
                    "$switch": {
                        "branches": [
                            {"case": {"$eq": ["$score.winner","away"]}, "then": "W"},
                            {"case": {"$eq": ["$score.winner","draw"]}, "then": "D"},
                            {"case": {"$eq": ["$score.winner","home"]}, "then": "L"},
                        ],
                        "default": "D"
                    }
                }
            }
        }},
        {"$project": {"rows": ["$home_row", "$away_row"]}},
        {"$unwind": "$rows"},
        {"$group": {
            "_id": "$rows.team_id",
            "played": {"$sum": 1},
            "wins":   {"$sum": {"$cond": [{"$eq": ["$rows.res","W"]}, 1, 0]}},
            "draws":  {"$sum": {"$cond": [{"$eq": ["$rows.res","D"]}, 1, 0]}},
            "losses": {"$sum": {"$cond": [{"$eq": ["$rows.res","L"]}, 1, 0]}},
            "gf":     {"$sum": "$rows.gf"},
            "ga":     {"$sum": "$rows.ga"}
        }},
        {"$addFields": {"gd": {"$subtract": ["$gf", "$ga"]},
                        "points": {"$add": [{"$multiply": ["$wins", 3]}, {"$multiply": ["$draws", 1]}]}}},
        {"$sort": {"points": -1, "gd": -1, "gf": -1, "_id": 1}},
        {"$lookup": {"from": "teams", "localField": "_id", "foreignField": "_id", "as": "team"}},
        {"$unwind": {"path": "$team", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 0,
            "team_id": {"$toString": "$_id"},
            "team_name": "$team.name",
            "played": 1, "wins": 1, "draws": 1, "losses": 1, "gf": 1, "ga": 1, "gd": 1, "points": 1
        }},
    ]
    table = list(db.matches.aggregate(pipeline))
    return jsonify({"competition_id": str(comp_id), "season_id": str(seas_id), "table": table}), 200

# ---------- LEGACY route (works with your matches.json) ----------

@tables_bp.get("/")
def league_table_legacy():
    """
    Legacy / JSON-driven table builder.

    Query params (same as before):
      competition / competition_like, season, date_from, date_to, round_to
      pts_win (3), pts_draw (1), pts_loss (0)
      breakdown=true -> include home_table, away_table + embed per-team home/away
      form=N (default 5)
    Expects documents with: team1, team2, score.ft: [home,away] (or '2-1' string)
    """
    # --- filters ---
    comp = request.args.get("competition")
    if comp: comp = comp.strip()
    comp_like = request.args.get("competition_like")
    season = request.args.get("season")
    if season: season = season.strip()

    q: Dict[str, Any] = {}
    if comp:        q["competition"] = comp
    elif comp_like: q["competition"] = Regex(comp_like, "i")
    if season:      q["season"] = season

    df = _iso(request.args.get("date_from"))
    dt = _iso(request.args.get("date_to"))
    if df and dt:   q["date"] = {"$gte": df, "$lte": dt}
    elif df:        q["date"] = {"$gte": df}
    elif dt:        q["date"] = {"$lte": dt}

    round_to = request.args.get("round_to")
    breakdown = str(request.args.get("breakdown", "false")).lower() in {"1", "true", "yes"}

    try:
        form_n = max(0, int(request.args.get("form", 5)))
        pts_win = int(request.args.get("pts_win", 3))
        pts_draw = int(request.args.get("pts_draw", 1))
        pts_loss = int(request.args.get("pts_loss", 0))
    except ValueError:
        return jsonify({"error": {"code": "BAD_REQUEST", "message": "Invalid numeric query param"}}), 400

    # --- fetch (legacy fields) ---
    proj = {"team1": 1, "team2": 1, "score": 1, "round": 1, "_id": 0}
    if "competition" in q: proj["competition"] = 1
    if "season" in q:      proj["season"] = 1
    if "date" in q:        proj["date"] = 1

    cursor = MATCHES.find(q, proj).sort([("date", 1), ("round", 1)])

    overall: Dict[str, Dict] = {}
    home: Dict[str, Dict] = {}
    away: Dict[str, Dict] = {}
    history: Dict[str, Deque[str]] = defaultdict(lambda: deque(maxlen=form_n if form_n else 0))

    included = 0
    for m in cursor:
        if round_to and isinstance(m.get("round"), str) and m["round"] > round_to:
            continue

        t1, t2 = m.get("team1"), m.get("team2")
        s = _parse_ft(m.get("score"))
        if not (t1 and t2 and s is not None):
            continue

        g1, g2 = s

        _ensure_row(overall, t1); _ensure_row(overall, t2)
        if breakdown:
            _ensure_row(home, t1); _ensure_row(away, t2)

        res_home = _tally_row(overall[t1], g1, g2, pts_win, pts_draw, pts_loss)
        _tally_row(overall[t2], g2, g1, pts_win, pts_draw, pts_loss)

        if breakdown:
            _tally_row(home[t1], g1, g2, pts_win, pts_draw, pts_loss)
            _tally_row(away[t2], g2, g1, pts_win, pts_draw, pts_loss)

        if form_n:
            history[t1].append(res_home)
            history[t2].append("W" if res_home == "L" else "L" if res_home == "W" else "D")

        included += 1

    overall_rows = sorted(overall.values(), key=_sort_key)
    for i, r in enumerate(overall_rows, start=1):
        r["position"] = i
        if form_n:
            seq = list(history.get(r["team"], []))
            r["form"] = seq
            r["form_str"] = "".join(seq)

    response: Dict[str, Any] = {
        "filters": {
            "competition": comp,
            "competition_like": comp_like,
            "season": season,
            "date_from": df, "date_to": dt, "round_to": round_to,
            "points": {"win": pts_win, "draw": pts_draw, "loss": pts_loss},
            "form": form_n, "breakdown": breakdown,
        },
        "matches_included": included,
        "table": overall_rows,
    }

    if breakdown:
        home_rows = sorted(home.values(), key=_sort_key)
        away_rows = sorted(away.values(), key=_sort_key)
        for i, r in enumerate(home_rows, start=1): r["position"] = i
        for i, r in enumerate(away_rows, start=1): r["position"] = i
        response["home_table"] = home_rows
        response["away_table"] = away_rows

        h_by = {r["team"]: r for r in home_rows}
        a_by = {r["team"]: r for r in away_rows}
        for r in overall_rows:
            t = r["team"]
            if t in h_by: r["home"] = _slim(h_by[t])
            if t in a_by: r["away"] = _slim(a_by[t])

    return jsonify(response), 200
