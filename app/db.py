from __future__ import annotations

from typing import Any, Dict

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from .config import config

_client: MongoClient | None = None

def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(config.MONGO_URI)
    return _client


def get_db() -> Database:
    client = get_client()
    db_name = config.MONGO_URI.rsplit("/", 1)[-1]
    return client[db_name]


def collection(name: str) -> Collection:
    return get_db()[name]


def ensure_indexes(db):
    # competitions
    db.competitions.create_index([("slug", 1)], unique=True, name="competitions_slug_uq")
    db.competitions.create_index([("country", 1), ("tier", 1)], name="competitions_country_tier")

    # seasons
    db.seasons.create_index([("competition_id", 1), ("slug", 1)], unique=True, name="seasons_comp_slug_uq")
    db.seasons.create_index([("competition_id", 1), ("start_date", 1)], name="seasons_comp_start")

    # teams
    db.teams.create_index([("slug", 1)], unique=True, name="teams_slug_uq")
    db.teams.create_index([("name", "text")], name="teams_name_text")
    db.teams.create_index([("stadium.location", "2dsphere")], name="teams_stadium_geo")

    # players
    db.players.create_index([("slug", 1)], unique=True, name="players_slug_uq")
    db.players.create_index([("name", "text")], name="players_name_text")
    db.players.create_index([("current_team_id", 1)], name="players_current_team")

    # matches
    # IMPORTANT: use *your* canonical date field; change "date" <-> "date_utc" if needed. Keep it consistent everywhere.
    db.matches.create_index([("competition_id", 1), ("season_id", 1), ("date", 1)], name="matches_comp_season_date")
    db.matches.create_index([("home_team_id", 1), ("date", 1)], name="matches_home_date")
    db.matches.create_index([("away_team_id", 1), ("date", 1)], name="matches_away_date")
    db.matches.create_index([("status", 1), ("date", 1)], name="matches_status_date")
    db.matches.create_index([("events.player_id", 1)], name="matches_events_player")
    db.matches.create_index([("events.team_id", 1)], name="matches_events_team")

    # notes (if you store notes separately)
    db.match_notes.create_index([("match_id", 1), ("created_at", -1)], name="notes_match_created")
    db.match_notes.create_index([("created_by.user_id", 1), ("created_at", -1)], name="notes_author_created")

    # users
    db.users.create_index([("username", 1)], unique=True, name="users_username_uq")
    db.users.create_index([("email", 1)], unique=True, name="users_email_uq")

    # blacklist
    db.blacklist.create_index([("token", 1)], unique=True, name="blacklist_token_uq")


    created: Dict[str, list[tuple[tuple[str, int], Dict[str, Any]]]] = {}
    for coll_name, index_list in indexes.items():
        coll = db[coll_name]
        created[coll_name] = []
        for keys, options in index_list:
            if keys and isinstance(keys[0], tuple):
                key_spec = list(keys)
            else:
                key_spec = [keys]
            if any(direction == "text" for _, direction in key_spec):
                key_spec = [(field, direction) for field, direction in key_spec]
            coll.create_index(key_spec, **options)
            created[coll_name].append((keys, options))
    return created
