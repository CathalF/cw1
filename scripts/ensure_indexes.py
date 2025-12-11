from pymongo import MongoClient, ASCENDING, TEXT

client = MongoClient("mongodb://localhost:27017/")
db = client.goalline

# Match indexes keep schedule lookups fast.
db.matches.create_index([("date", ASCENDING)])
db.matches.create_index([("team1", ASCENDING)])
db.matches.create_index([("team2", ASCENDING)])
db.matches.create_index([("round", ASCENDING)])

# Teams benefit from a text index for flexible search.
db.teams.create_index([("name", TEXT)], default_language="english")

# Players get text search plus a few handy foreign-key indexes.
db.players.create_index([("name", TEXT)], default_language="english")
db.players.create_index([("team", ASCENDING)])
db.players.create_index([("mongo_team_id", ASCENDING)])

print("Indexes ensured.")
