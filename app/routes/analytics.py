from __future__ import annotations

from flask import Blueprint, request, jsonify
from bson import Regex
from datetime import datetime
from collections import defaultdict, deque
import re

from ..db import collection

analytics_bp = Blueprint("analytics", __name__)
MATCHES = collection("matches")

# ------------ helpers ------------

def _iso(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date().isoformat()
    except Exception:
        return None

_score_pat = re.compile(r"^\s*(\d+)\D+(\d+)\s*$")

def _parse_score(score):
    # accepts '2-1' or {'ft':[2,1]}
    if isinstance(score, dict):
        ft = score.get("ft")
        if isinstance(ft, list) and len(ft) == 2:
            try:
                return int(ft[0]), int(ft[1])
            except Exception:
                return None
    if isinstance(score, str):
        m = _score_pat.match(score)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None

def _base_query_from_args():
    q = {}
    comp = request.args.get("competition")
    if comp:
        q["competition"] = comp.strip()
    comp_like = request.args.get("competition_like")
    if comp_like and "competition" not in q:
        q["competition"] = Regex(comp_like, "i")

    season = request.args.get("season")
    if season:
        q["season"] = season.strip()

    df = _iso(request.args.get("date_from"))
    dt = _iso(request.args.get("date_to"))
    if df and dt:   q["date"] = {"$gte": df, "$lte": dt}
    elif df:        q["date"] = {"$gte": df}
    elif dt:        q["date"] = {"$lte": dt}

    round_to = request.args.get("round_to")
    return q, round_to, df, dt

def _fetch_matches(q, round_to):
    proj = {"team1":1, "team2":1, "score":1, "round":1, "date":1, "_id":0}
    cursor = MATCHES.find(q, proj).sort([("date", 1), ("round", 1)])
    for m in cursor:
        if round_to and isinstance(m.get("round"), str) and m["round"] > round_to:
            continue
        s = _parse_score(m.get("score"))
        if not s:
            continue  # ignore fixtures with no FT score
        yield {**m, "score_ft": s}

# ------------ /h2h ------------

@analytics_bp.get("/h2h")
def head_to_head():
    """
    GET /api/v1/analytics/h2h?team1=...&team2=...&competition=...&season=...
    Returns summary and the list of relevant matches (chronological).
    """
    team1 = request.args.get("team1")
    team2 = request.args.get("team2")
    if not team1 or not team2:
        return jsonify({"error":{"code":"BAD_REQUEST","message":"team1 and team2 are required"}}), 400

    q, round_to, df, dt = _base_query_from_args()
    # constrain to the two teams (either order)
    q["$or"] = [{"team1": team1, "team2": team2},
                {"team1": team2, "team2": team1}]

    results = {"team1": team1, "team2": team2, "played": 0,
               "wins": {team1:0, team2:0}, "draws": 0,
               "goals": {team1:0, team2:0}}

    matches = []
    for m in _fetch_matches(q, round_to):
        a, b = m["team1"], m["team2"]
        g1, g2 = m["score_ft"]
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
        "filters": {"team1": team1, "team2": team2,
                    "date_from": df, "date_to": dt, "round_to": round_to},
        "summary": results,
        "matches": matches
    })

# ------------ /streaks ------------

@analytics_bp.get("/streaks")
def streaks():
    """
    GET /api/v1/analytics/streaks?type=winning|unbeaten|winless|scoring|clean&limit=10
    Computes best current streaks per team within filters (competition/season/date, etc.)
    """
    typ = (request.args.get("type") or "winning").lower()
    limit = max(1, min(50, int(request.args.get("limit", 10))))

    q, round_to, df, dt = _base_query_from_args()
    matches = list(_fetch_matches(q, round_to))

    # build chronological results per team (overall, not split by home/away)
    sequences = defaultdict(list)  # team -> list of result codes "W/L/D" plus goals info
    for m in matches:
        a, b = m["team1"], m["team2"]
        g1, g2 = m["score_ft"]
        # result code from home perspective
        ra = "W" if g1 > g2 else "L" if g1 < g2 else "D"
        rb = "W" if ra == "L" else "L" if ra == "W" else "D"
        sequences[a].append((ra, g1, g2))
        sequences[b].append((rb, g2, g1))

    def _current_streak(seq, mode):
        """
        mode:
          - winning: consecutive W
          - unbeaten: consecutive W/D
          - winless: consecutive L/D
          - scoring: consecutive games with gf > 0
          - clean:   consecutive games with ga = 0
        returns (length, gf_sum, ga_sum)
        """
        n = 0; gf = 0; ga = 0
        for r, gfor, gagainst in reversed(seq):  # from most recent backwards
            ok = (
                (mode == "winning"  and r == "W") or
                (mode == "unbeaten" and r in ("W","D")) or
                (mode == "winless"  and r in ("L","D")) or
                (mode == "scoring"  and gfor > 0) or
                (mode == "clean"    and gagainst == 0)
            )
            if not ok:
                break
            n += 1; gf += gfor; ga += gagainst
        return n, gf, ga

    rows = []
    for team, seq in sequences.items():
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
    GET /api/v1/analytics/form?n=5&by=overall|home|away&team=<optional>
    Returns last-N form per team (or a single team if provided).
    """
    n = max(1, min(20, int(request.args.get("n", 5))))
    by = (request.args.get("by") or "overall").lower()
    team_filter = request.args.get("team")

    q, round_to, df, dt = _base_query_from_args()
    matches = list(_fetch_matches(q, round_to))

    hist = defaultdict(lambda: deque(maxlen=n))

    for m in matches:
        a, b = m["team1"], m["team2"]
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

    rows.sort(key=lambda r: (-(r["form_str"].count("W")), -len(r["form_str"]), r["team"]))
    return jsonify({
        "filters": {"n": n, "by": by, "team": team_filter, "date_from": df, "date_to": dt, "round_to": round_to},
        "data": rows
    })
