from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from datetime import datetime, timedelta
import asyncio
import random
import logging
from config import MONGO_DB_URI, API_ID, API_HASH, BOT_TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Client("werewolf_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

mongo_client = MongoClient(MONGO_DB_URI)
db = mongo_client["werewolf_bot"]
games_col = db.games
players_col = db.players

JOIN_TIME = 40
MIN_PLAYERS = 6
MAX_PLAYERS = 16

ROLE_WEREWOLF = "werewolf"
ROLE_VILLAGER = "villager"

POWER_COSTS = {
    "disguise": 5,
}

async def reset_game(chat_id):
    games_col.update_one({"chat_id": chat_id, "active": True}, {"$set": {"active": False, "phase": "stopped"}})
    players_col.update_many({"game_chat": chat_id}, {"$unset": {"role": "", "game_id": "", "disguised": "", "coins": ""}})

def generate_roles(num):
    werewolves = max(1, num // 4)
    villagers = num - werewolves
    roles = [ROLE_WEREWOLF] * werewolves + [ROLE_VILLAGER] * villagers
    random.shuffle(roles)
    return roles

async def give_coins(player_id, amount):
    player = players_col.find_one({"_id": player_id})
    if not player:
        players_col.insert_one({"_id": player_id, "coins": amount})
    else:
        players_col.update_one({"_id": player_id}, {"$inc": {"coins": amount}})

def get_coins(player_id):
    player = players_col.find_one({"_id": player_id})
    return player.get("coins", 0) if player else 0

@app.on_message(filters.command("startgame") & filters.group)
async def start_game(client, message):
    chat_id = message.chat.id
    if games_col.find_one({"chat_id": chat_id, "active": True}):
        await message.reply("❌ Game already running. Use /stopgame to stop.")
        return

    game_data = {
        "chat_id": chat_id,
        "active": True,
        "players": [],
        "phase": "lobby",
        "start_time": datetime.utcnow(),
        "night_duration": timedelta(minutes=2),
        "day_duration": timedelta(minutes=5),
        "votes": {},
        "lynch_target": None,
    }
    game_id = games_col.insert_one(game_data).inserted_id

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📝 Join Game", callback_data=f"join_{game_id}")]]
    )
    await message.reply(f"🎲 Game started! Join in {JOIN_TIME} seconds (min {MIN_PLAYERS}, max {MAX_PLAYERS}).", reply_markup=keyboard)

    await asyncio.sleep(JOIN_TIME)

    game = games_col.find_one({"_id": game_id})
    players = game.get("players", [])

    if len(players) < MIN_PLAYERS:
        games_col.update_one({"_id": game_id}, {"$set": {"active": False, "phase": "cancelled"}})
        await client.send_message(chat_id, f"❌ Not enough players ({len(players)}/{MIN_PLAYERS}). Game cancelled.")
        return

    roles = generate_roles(len(players))

    for pid, role in zip(players, roles):
        players_col.update_one({"_id": pid}, {"$set": {"role": role, "game_id": game_id, "game_chat": chat_id, "coins": 10, "disguised": False}}, upsert=True)

    games_col.update_one({"_id": game_id}, {"$set": {"phase": "night"}})
    await client.send_message(chat_id, f"🌙 Night phase begins! Werewolves, choose your victim.")

    await asyncio.sleep(game["night_duration"].total_seconds())

    game = games_col.find_one({"_id": game_id})
    if game["phase"] == "night":
        games_col.update_one({"_id": game_id}, {"$set": {"phase": "day"}})
        await client.send_message(chat_id, f"🌞 Day phase begins! Discuss and vote to lynch a player.")

        await asyncio.sleep(game["day_duration"].total_seconds())

        game = games_col.find_one({"_id": game_id})
        if game["phase"] == "day":
            games_col.update_one({"_id": game_id}, {"$set": {"phase": "voting"}})
            await client.send_message(chat_id, f"🗳️ Voting phase begins! Vote to lynch a player.")

            # Implement voting logic here

            games_col.update_one({"_id": game_id}, {"$set": {"phase": "night"}})
            await client.send_message(chat_id, f"🌙 Night phase begins! Werewolves, choose your victim.")

            await asyncio.sleep(game["night_duration"].total_seconds())

            game = games_col.find_one({"_id": game_id})
            if game["phase"] == "night":
                games_col.update_one({"_id": game_id}, {"$set": {"phase": "day"}})
                await client.send_message(chat_id, f"🌞 Day phase begins! Discuss and vote to lynch a player.")

                await asyncio.sleep(game["day_duration"].total_seconds())

                # Repeat the cycle

@app.on_callback_query(filters.regex(r"join_"))
async def join_game(client, callback):
    user_id = callback.from_user.id
    game_id = callback.data.split("_")[1]

    from bson import ObjectId
    game_id =32