from pymongo import MongoClient, ASCENDING, TEXT

client = MongoClient("mongodb://localhost:27017/")
db = client.goalline

# matches
db.matches.create_index([("date", ASCENDING)])
db.matches.create_index([("team1", ASCENDING)])
db.matches.create_index([("team2", ASCENDING)])
db.matches.create_index([("round", ASCENDING)])

# teams
db.teams.create_index([("name", TEXT)], default_language="english")

# players
db.players.create_index([("name", TEXT)], default_language="english")
db.players.create_index([("team", ASCENDING)])
db.players.create_index([("mongo_team_id", ASCENDING)])

print("Indexes ensured.")
