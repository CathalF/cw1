from pathlib import Path
import json, re
from datetime import datetime
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "goalline"  # Tweak this when loading into a different database.

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def to_iso(d):
    """Return YYYY-MM-DD or None."""
    if not d:
        return None
    try:
        return datetime.fromisoformat(d).date().isoformat()
    except Exception:
        return None


def normalize_score(score):
    """
    Return:
      {"ft": {"home": int, "away": int}, "ht": {"home": int, "away": int}} (ht optional)
    Accepts any of:
      - {"ft":[h,a], "ht":[h,a]}
      - {"ft":{"home":h,"away":a}, "ht":{"home":h,"away":a}}
      - "h-a" (string)
    """
    out = {}

    # Structured payloads with ft/ht keys.
    if isinstance(score, dict):
        ft = score.get("ft")
        if isinstance(ft, list) and len(ft) == 2:
            out["ft"] = {"home": int(ft[0]), "away": int(ft[1])}
        elif isinstance(ft, dict):
            out["ft"] = {"home": int(ft.get("home", 0)), "away": int(ft.get("away", 0))}

        ht = score.get("ht")
        if isinstance(ht, list) and len(ht) == 2:
            out["ht"] = {"home": int(ht[0]), "away": int(ht[1])}
        elif isinstance(ht, dict):
            out["ht"] = {"home": int(ht.get("home", 0)), "away": int(ht.get("away", 0))}

        return out if "ft" in out else None

    # Handle simple "h-a" score strings.
    if isinstance(score, str):
        m = re.match(r"^\s*(\d+)\D+(\d+)\s*$", score)
        if m:
            return {"ft": {"home": int(m.group(1)), "away": int(m.group(2))}}

    return None


def load_simple(name):
    path = DATA_DIR / f"{name}.json"
    if not path.exists():
        return 0
    docs = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(docs, dict) and "data" in docs:
        docs = docs["data"]
    if not isinstance(docs, list):
        return 0
    if docs:
        db[name].delete_many({})  # Clear existing documents so we reload from scratch.
        db[name].insert_many(docs)
    return len(docs)


def load_matches():
    path = DATA_DIR / "matches.json"
    if not path.exists():
        return 0

    raw = json.loads(path.read_text(encoding="utf-8"))

    # Input can be either {"name": ..., "matches": [...]} or a bare list of matches.
    comp_name = None
    matches = []
    if isinstance(raw, dict) and "matches" in raw:
        comp_name = raw.get("name")
        matches = raw["matches"] if isinstance(raw["matches"], list) else []
    elif isinstance(raw, list):
        matches = raw

    # Pull a season token from names like "Competition 2025/26" when possible.
    parsed_season = None
    if isinstance(comp_name, str):
        m = re.search(r"(\d{4}\s*/\s*\d{2})$", comp_name)
        if m:
            parsed_season = m.group(1).replace(" ", "")
            comp_name = comp_name[: m.start()].strip()

    out = []
    comp_ids_seen = set()
    season_ids_seen = set()

    for m in matches:
        doc = dict(m)  # Shallow copy so we can tweak fields safely.

        # Normalise the date field into YYYY-MM-DD.
        doc["date"] = to_iso(m.get("date"))

        # Tidy score representations into our canonical structure.
        ns = normalize_score(m.get("score"))
        if ns:
            doc["score"] = ns
        else:
            doc.pop("score", None)

        # Keep explicit *_id values but backfill friendly names when they are missing.
        if comp_name and "competition" not in doc:
            doc["competition"] = comp_name
        if parsed_season and "season" not in doc:
            doc["season"] = parsed_season

        # Track identifiers so we can build a precise delete filter later.
        if isinstance(doc.get("competition_id"), str):
            comp_ids_seen.add(doc["competition_id"])
        if isinstance(doc.get("season_id"), str):
            season_ids_seen.add(doc["season_id"])

        # Strip out keys with None values to keep documents lean.
        doc = {k: v for k, v in doc.items() if v is not None}
        out.append(doc)

    if not out:
        return 0

    # Replace existing docs when we can uniquely identify the dataset by ids.
    delete_filter = {}
    if len(comp_ids_seen) == 1:
        delete_filter["competition_id"] = next(iter(comp_ids_seen))
    if len(season_ids_seen) == 1:
        delete_filter["season_id"] = next(iter(season_ids_seen))

    if delete_filter:
        db.matches.delete_many(delete_filter)
    else:
        db.matches.delete_many({})

    db.matches.insert_many(out)
    return len(out)


def ensure_indexes():
    # Indexes for the newer schema fields.
    db.matches.create_index([("date", 1)])
    db.matches.create_index([("competition_id", 1), ("season_id", 1)])
    db.matches.create_index([("home_team_id", 1)])
    db.matches.create_index([("away_team_id", 1)])
    # Handy indexes for the legacy structure in case you still query it.
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
    print(
        f"Loaded: matches={n_matches}, teams={n_teams}, players={n_players}, "
        f"competitions={n_comp}, seasons={n_seasons}"
    )


if __name__ == "__main__":
    main()
