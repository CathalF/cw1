from __future__ import annotations

from flask import Blueprint, request, jsonify
from bson import Regex
from datetime import datetime
from collections import defaultdict, deque
from typing import Any, Dict, Iterator, Tuple, Optional
import re

from ..db import collection

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/v1/analytics")
MATCHES = collection("matches")

# ------------ helpers ------------

def _iso(s: str | None) -> Optional[str]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date().isoformat()
    except Exception:
        return None

# Accept "2-1" (any non-digit separator)

_SCORE_RE = re.compile(r"^\s*(\d+)\D+(\d+)\s*$")

def _parse_score(score):
    """
    Return (home, away) or None.
    Accepts: "2-1", {"ft":[h,a]}, {"ft":{"home":h,"away":a}}
    """
    if score is None:
        return None

    if isinstance(score, dict):
        ft = score.get("ft")
        if isinstance(ft, list) and len(ft) == 2:
            try:
                return int(ft[0]), int(ft[1])
            except Exception:
                return None
        if isinstance(ft, dict):
            try:
                return int(ft.get("home")), int(ft.get("away"))
            except Exception:
                return None

    if isinstance(score, str):
        m = _SCORE_RE.match(score)  # <-- no space here
        if m:
            return int(m.group(1)), int(m.group(2))

    return None

def _pick_team_fields(m: Dict[str, Any]) -> Tuple[str, str]:
    """
    Prefer IDs; fall back to names; finally legacy team1/team2.
    """
    a = m.get("home_team_id") or m.get("home_team") or m.get("team1")
    b = m.get("away_team_id") or m.get("away_team") or m.get("team2")
    return str(a), str(b)

def _base_query_from_args():
    """
    Build a query compatible with both schemas.
    Supported filters:
      - legacy: competition, competition_like, season
      - new:    competition_id, season_id, team_id (matches either home/away), status
      - dates:  date_from/date_to (works for ISO strings or datetimes)
      - round_to: skip matches with round > round_to (string compare, legacy only)
    """
    q: Dict[str, Any] = {}

    # legacy
    comp = request.args.get("competition")
    if comp:
        q["competition"] = comp.strip()
    comp_like = request.args.get("competition_like")
    if comp_like and "competition" not in q:
        q["competition"] = Regex(comp_like, "i")
    season = request.args.get("season")
    if season:
        q["season"] = season.strip()

    # new
    comp_id = request.args.get("competition_id")
    if comp_id:
        q["competition_id"] = comp_id.strip()
    season_id = request.args.get("season_id")
    if season_id:
        q["season_id"] = season_id.strip()
    team_id = request.args.get("team_id")
    if team_id:
        q["$or"] = [{"home_team_id": team_id.strip()}, {"away_team_id": team_id.strip()}]
    status = request.args.get("status")
    if status:
        q["status"] = status.strip()

    # dates
    df = _iso(request.args.get("date_from"))
    dt = _iso(request.args.get("date_to"))
    if df and dt:
        q["date"] = {"$gte": df, "$lte": dt}
    elif df:
        q["date"] = {"$gte": df}
    elif dt:
        q["date"] = {"$lte": dt}

    round_to = request.args.get("round_to")
    return q, round_to, df, dt

def _fetch_matches(q: Dict[str, Any], round_to: Optional[str]) -> Iterator[Dict[str, Any]]:
    """
    Yields normalized match dicts with:
      - teamA, teamB (IDs if available else names)
      - score_ft: (h, a)
      - date, round (if present)
    Skips unplayed matches (no valid FT score).
    """
    proj = {
        # new schema
        "home_team_id": 1, "away_team_id": 1,
        "home_team": 1, "away_team": 1,
        "competition_id": 1, "season_id": 1,
        "status": 1,
        # legacy
        "team1": 1, "team2": 1,
        "competition": 1, "season": 1,
        # common
        "score": 1, "round": 1, "date": 1, "_id": 0
    }
    cursor = MATCHES.find(q, proj).sort([("date", 1), ("round", 1)])
    for m in cursor:
        # legacy cutoff by round lexicographically (as your original)
        if round_to and isinstance(m.get("round"), str) and m["round"] > round_to:
            continue

        s = _parse_score(m.get("score"))
        if s is None:
            continue  # ignore fixtures with no FT score

        a, b = _pick_team_fields(m)
        yield {
            "date": m.get("date"),
            "round": m.get("round"),
            "teamA": a,
            "teamB": b,
            "score_ft": s,
        }

# ------------ /h2h ------------

@analytics_bp.get("/h2h")
def head_to_head():
    """
    GET /api/v1/analytics/h2h?team1=...&team2=...
    Optional filters: competition_id/season_id (new) or competition/season (legacy),
    date_from/date_to, round_to, status.
    """
    t1 = (request.args.get("team1") or "").strip()
    t2 = (request.args.get("team2") or "").strip()
    if not t1 or not t2:
        return jsonify({"error":{"code":"BAD_REQUEST","message":"team1 and team2 are required"}}), 400

    # Base filters (competition/season/date/status etc.)
    q, round_to, df, dt = _base_query_from_args()

    # Only fetch matches that *could* involve either team (fast pre-filter).
    # Works for both schemas (IDs or names).
    teams_or = [
        {"home_team_id": {"$in": [t1, t2]}},
        {"away_team_id": {"$in": [t1, t2]}},
        {"home_team":   {"$in": [t1, t2]}},
        {"away_team":   {"$in": [t1, t2]}},
        {"team1":       {"$in": [t1, t2]}},
        {"team2":       {"$in": [t1, t2]}},
    ]
    if "$or" in q:
        # merge with any existing "$or" (e.g., team_id); keep both using AND
        q = {"$and": [ {k:v for k,v in q.items() if k != "$or"}, {"$or": q["$or"]}, {"$or": teams_or} ]}
    else:
        q["$or"] = teams_or

    results = {
        "team1": t1, "team2": t2, "played": 0,
        "wins": {t1: 0, t2: 0}, "draws": 0,
        "goals": {t1: 0, t2: 0}
    }
    matches = []

    for m in _fetch_matches(q, round_to):
        a, b = m["teamA"], m["teamB"]
        g1, g2 = m["score_ft"]

        # STRICT check: this fixture must be exactly these two teams
        if {a, b} != {t1, t2}:
            continue

        results["played"] += 1
        results["goals"][a] += g1
        results["goals"][b] += g2

        if g1 > g2:
            results["wins"][a] += 1
        elif g2 > g1:
            results["wins"][b] += 1
        else:
            results["draws"] += 1

        matches.append({
            "date": m.get("date"),
            "round": m.get("round"),
            "team1": a, "team2": b,
            "score": f"{g1}-{g2}"
        })

    return jsonify({
        "filters": {
            "team1": t1, "team2": t2,
            "date_from": df, "date_to": dt, "round_to": round_to
        },
        "summary": results,
        "matches": matches
    }), 200

# ------------ /streaks ------------

@analytics_bp.get("/streaks")
def streaks():
    """
    GET /api/v1/analytics/streaks
      ?type=winning|unbeaten|winless|scoring|clean
      &limit=10
      (+ same filters as _base_query_from_args)
    """
    typ = (request.args.get("type") or "winning").lower()
    limit = max(1, min(50, int(request.args.get("limit", 10))))

    q, round_to, df, dt = _base_query_from_args()
    matches = list(_fetch_matches(q, round_to))

    # chronological sequences per team (overall; home perspective vs away perspective)
    seqs = defaultdict(list)  # team -> [(res, gf, ga), ...]
    for m in matches:
        a, b = m["teamA"], m["teamB"]
        g1, g2 = m["score_ft"]
        ra = "W" if g1 > g2 else "L" if g1 < g2 else "D"
        rb = "W" if ra == "L" else "L" if ra == "W" else "D"
        seqs[a].append((ra, g1, g2))
        seqs[b].append((rb, g2, g1))

    def _current_streak(seq, mode):
        n = 0; gf = 0; ga = 0
        for r, gfor, gagainst in reversed(seq):
            ok = (
                (mode == "winning"  and r == "W") or
                (mode == "unbeaten" and r in ("W", "D")) or
                (mode == "winless"  and r in ("L", "D")) or
                (mode == "scoring"  and gfor > 0) or
                (mode == "clean"    and gagainst == 0)
            )
            if not ok:
                break
            n += 1; gf += gfor; ga += gagainst
        return n, gf, ga

    rows = []
    for team, seq in seqs.items():
        length, gf, ga = _current_streak(seq, typ)
        rows.append({"team": team, "length": length, "gf": gf, "ga": ga})

    rows.sort(key=lambda r: (-r["length"], -r["gf"], r["ga"], r["team"]))
    return jsonify({
        "filters": {"type": typ, "limit": limit, "date_from": df, "date_to": dt, "round_to": round_to},
        "streaks": rows[:limit]
    })

# ------------ /form ------------

@analytics_bp.get("/form")
def form():
    """
    GET /api/v1/analytics/form
      ?n=5
      &by=overall|home|away
      &team=<optional team id or name>
      (+ same filters as _base_query_from_args)
    """
    n = max(1, min(20, int(request.args.get("n", 5))))
    by = (request.args.get("by") or "overall").lower()
    team_filter = request.args.get("team")

    q, round_to, df, dt = _base_query_from_args()
    matches = list(_fetch_matches(q, round_to))

    hist = defaultdict(lambda: deque(maxlen=n))

    for m in matches:
        a, b = m["teamA"], m["teamB"]
        g1, g2 = m["score_ft"]
        ra = "W" if g1 > g2 else "L" if g1 < g2 else "D"
        rb = "W" if ra == "L" else "L" if ra == "W" else "D"

        if by in ("overall", "home"):
            hist[a].append(ra)
        if by in ("overall", "away"):
            hist[b].append(rb)

    rows = []
    for t, seq in hist.items():
        if team_filter and t != team_filter:
            continue
        rows.append({"team": t, "n": n, "form": list(seq), "form_str": "".join(seq)})

    # Sort by most Ws in window, then by string length (all equal to n), then team
    rows.sort(key=lambda r: (-r["form"].count("W"), r["team"]))
    return jsonify({
        "filters": {"n": n, "by": by, "team": team_filter,
                    "date_from": df, "date_to": dt, "round_to": round_to},
        "data": rows
    })
