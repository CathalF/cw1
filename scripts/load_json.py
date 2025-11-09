# scripts/load_json.py
from pathlib import Path
import json, re
from datetime import datetime
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "goalline"  # change if needed

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

def to_iso(d):
    if not d:
        return None
    try:
        return datetime.fromisoformat(d).date().isoformat()
    except Exception:
        return None

def score_to_str(score):
    if isinstance(score, dict) and isinstance(score.get("ft"), list) and len(score["ft"]) == 2:
        h, a = score["ft"]
        return f"{int(h)}-{int(a)}"
    if isinstance(score, str):
        m = re.match(r"^\s*(\d+)\D+(\d+)\s*$", score)
        if m:
            return f"{int(m.group(1))}-{int(m.group(2))}"
    return None

def load_simple(name):
    path = DATA_DIR / f"{name}.json"
    if not path.exists(): return 0
    docs = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(docs, dict) and "data" in docs:
        docs = docs["data"]
    if not isinstance(docs, list): return 0
    if docs:
        db[name].delete_many({})      # replace-all for simplicity
        db[name].insert_many(docs)
    return len(docs)

def load_matches():
    path = DATA_DIR / "matches.json"
    if not path.exists(): return 0
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Accept either: {"name": "...", "matches":[...]} OR a plain list of matches
    if isinstance(raw, dict) and "matches" in raw:
        comp_name = raw.get("name")
        matches = raw["matches"]
    else:
        comp_name = None
        matches = raw if isinstance(raw, list) else []

    # Try to parse season from comp_name like "... 2025/26"
    season = None
    if isinstance(comp_name, str):
        m = re.search(r"(\d{4}\s*/\s*\d{2})$", comp_name)
        if m:
            season = m.group(1).replace(" ", "")
            comp_name = comp_name[: m.start()].strip()

    out = []
    for m in matches:
        doc = dict(m)  # copy
        doc["date"] = to_iso(m.get("date"))
        if comp_name:  doc["competition"] = comp_name
        if season:     doc["season"] = season
        s = score_to_str(m.get("score"))
        if s: doc["score"] = s
        # remove None fields
        doc = {k: v for k, v in doc.items() if v is not None}
        out.append(doc)

    if out:
        q = {}
        if comp_name: q["competition"] = comp_name
        if season:    q["season"] = season
        if q: db.matches.delete_many(q)
        else: db.matches.delete_many({})
        db.matches.insert_many(out)
    return len(out)

def ensure_indexes():
    db.matches.create_index([("date", 1)])
    db.matches.create_index([("competition", 1), ("season", 1)])
    db.matches.create_index([("team1", 1)])
    db.matches.create_index([("team2", 1)])

def main():
    n_matches = load_matches()
    n_teams = load_simple("teams")
    n_players = load_simple("players")
    n_comp = load_simple("competitions")
    n_seasons = load_simple("seasons")
    ensure_indexes()
    print(f"Loaded: matches={n_matches}, teams={n_teams}, players={n_players}, competitions={n_comp}, seasons={n_seasons}")

if __name__ == "__main__":
    main()
