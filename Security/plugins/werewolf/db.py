from pymongo import MongoClient
from config import MONGO_DB_URI

mongo_client = MongoClient(MONGO_DB_URI)
db = mongo_client["werewolf_bot"]
games_col = db.games
players_col = db.players
actions_col = db.actions
