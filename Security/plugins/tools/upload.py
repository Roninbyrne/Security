from pyrogram import Client, filters
from Security import app
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pymongo import MongoClient
from datetime import datetime, timedelta
import asyncio
import random
import logging
from config import MONGO_DB_URI, API_ID, API_HASH, BOT_TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mongo_client = MongoClient(MONGO_DB_URI)
db = mongo_client["werewolf_bot"]
games_col = db.games
players_col = db.players

JOIN_TIME = 60
MIN_PLAYERS = 4
MAX_PLAYERS = 16

ROLE_WEREWOLF = "werewolf"
ROLE_VILLAGER = "villager"
ROLE_ALPHA = "alpha"
ROLE_DOCTOR = "doctor"

async def reset_game(chat_id):
    games_col.update_one({"chat_id": chat_id, "active": True}, {"$set": {"active": False, "phase": "stopped"}})
    players_col.update_many({"game_chat": chat_id}, {"$unset": {"role": "", "game_id": "", "disguised": ""}})

def generate_roles(num):
    roles = []
    if num >= 8:
        roles.append(ROLE_ALPHA)
        roles.append(ROLE_DOCTOR)
        werewolves = max(1, (num - 2) // 4)
        villagers = num - (werewolves + 2)
        roles.extend([ROLE_WEREWOLF] * werewolves)
        roles.extend([ROLE_VILLAGER] * villagers)
    else:
        werewolves = max(1, num // 4)
        villagers = num - werewolves
        roles = [ROLE_WEREWOLF] * werewolves + [ROLE_VILLAGER] * villagers
    random.shuffle(roles)
    return roles

async def day_night_cycle(chat_id, game_id):
    while True:
        game = games_col.find_one({"_id": game_id, "active": True})
        if not game:
            break
        current_phase = game.get("day_night", "day")
        next_phase = "night" if current_phase == "day" else "day"
        games_col.update_one({"_id": game_id}, {"$set": {"day_night": next_phase}})
        await app.send_message(chat_id, f"🌗 It's now *{next_phase.upper()}* time!", parse_mode=ParseMode.MARKDOWN)
        await asyncio.sleep(60)

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
        "day_night": "day",
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
        players_col.update_one({"_id": pid}, {"$set": {"role": role, "game_id": game_id, "game_chat": chat_id, "disguised": False}}, upsert=True)

    games_col.update_one({"_id": game_id}, {"$set": {"phase": "started"}})

    player_lines = []
    for i, pid in enumerate(players):
        user = await client.get_users(pid)
        player_lines.append(f"{i+1}. [{user.first_name}](tg://user?id={pid})")

    await client.send_message(
        chat_id,
        f"✅ Game started with {len(players)} players!\n" + "\n".join(player_lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("CHECK UR ROLE", callback_data=f"bulkrole_{game_id}")]])
    )

    asyncio.create_task(day_night_cycle(chat_id, game_id))

    for pid in players:
        try:
            await client.send_message(
                pid,
                "🎭 Game started! Press below to reveal your role.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Reveal Role", callback_data=f"reveal_{game_id}")]
                ])
            )
        except Exception:
            try:
                user = await client.get_users(pid)
                await client.send_message(
                    chat_id,
                    f"⚠️ Couldn't DM [{user.first_name}](tg://user?id={pid}). Ask them to start the bot in private chat.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                pass

@app.on_callback_query(filters.regex(r"join_"))
async def join_game(client, callback):
    user_id = callback.from_user.id
    game_id = callback.data.split("_")[1]
    from bson import ObjectId
    game_id = ObjectId(game_id)

    game = games_col.find_one({"_id": game_id})
    if not game or not game.get("active") or game.get("phase") != "lobby":
        await callback.answer("❌ Not accepting joins.", show_alert=True)
        return

    players = game.get("players", [])
    if user_id in players:
        await callback.answer("✅ Already joined.")
        return

    if len(players) >= MAX_PLAYERS:
        await callback.answer("❌ Game full.")
        return

    players.append(user_id)
    games_col.update_one({"_id": game_id}, {"$set": {"players": players}})
    await callback.answer(f"✅ Joined! Total: {len(players)}")

@app.on_callback_query(filters.regex(r"reveal_"))
async def reveal_role(client, callback):
    user_id = callback.from_user.id
    game_id = callback.data.split("_")[1]
    from bson import ObjectId
    game_id = ObjectId(game_id)

    player = players_col.find_one({"_id": user_id, "game_id": game_id})
    if not player:
        await callback.answer("❌ Not in this game.", show_alert=True)
        return

    role = player.get("role", "Unknown").capitalize()
    disguised = player.get("disguised", False)

    text = f"🎭 Role: *{role}*\n"
    if disguised:
        text += "🕵️‍♂️ You are currently disguised.\n"

    await callback.answer()
    await callback.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command("stopgame") & filters.group)
async def stop_game(client, message):
    chat_id = message.chat.id
    game = games_col.find_one({"chat_id": chat_id, "active": True})
    if not game:
        await message.reply("❌ No active game.")
        return

    await reset_game(chat_id)
    await message.reply("🛑 Game stopped by admin.")

@app.on_message(filters.group & filters.text & ~filters.service)
async def suppress_messages_at_night(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    game = games_col.find_one({"chat_id": chat_id, "active": True})
    if not game or game.get("phase") != "started":
        return

    if game.get("day_night") == "night":
        await message.delete()

if __name__ == "__main__":
    app.run()