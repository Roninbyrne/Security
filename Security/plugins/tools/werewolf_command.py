from Security import app
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from plugins.tools.db import games_col, players_col
from plugins.tools.config import JOIN_TIME, MIN_PLAYERS, MAX_PLAYERS
from plugins.tools.werewolf_core import generate_roles, reset_game, day_night_cycle
from datetime import datetime
import asyncio

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
        players_col.update_one({"_id": pid}, {"$set": {
            "role": role,
            "game_id": game_id,
            "game_chat": chat_id,
            "disguised": False,
            "healed_times": 0
        }}, upsert=True)

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
        except:
            user = await client.get_users(pid)
            await client.send_message(
                chat_id,
                f"⚠️ Couldn't DM [{user.first_name}](tg://user?id={pid}). Ask them to start the bot in private chat.",
                parse_mode=ParseMode.MARKDOWN
            )

@app.on_message(filters.command("stopgame") & filters.group)
async def stop_game(client, message):
    chat_id = message.chat.id
    game = games_col.find_one({"chat_id": chat_id, "active": True})
    if not game:
        await message.reply("❌ No active game.")
        return

    await reset_game(chat_id)
    await message.reply("🛑 Game stopped by admin.")