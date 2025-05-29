from pyrogram import Client, filters
from Security import app
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pymongo import MongoClient
from datetime import datetime, timedelta
import asyncio
import random
import logging
from config import MONGO_DB_URI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mongo_client = MongoClient(MONGO_DB_URI)
db = mongo_client["werewolf_bot"]
games_col = db.games
players_col = db.players
actions_col = db.actions

JOIN_TIME = 60
MIN_PLAYERS = 4
MAX_PLAYERS = 16

ROLE_WEREWOLF = "werewolf"
ROLE_VILLAGER = "villager"
ROLE_ALPHA = "alpha"
ROLE_DOCTOR = "doctor"
ROLE_SPY = "spy"

async def reset_game(chat_id):
    games_col.update_one({"chat_id": chat_id, "active": True}, {"$set": {"active": False, "phase": "stopped"}})
    players_col.update_many({"game_chat": chat_id}, {"$unset": {"role": "", "game_id": "", "disguised": "", "healed_times": "", "spy_once_used": ""}})
    actions_col.delete_many({"chat_id": chat_id})

def generate_roles(num):
    roles = []
    if num >= 8:
        roles.append(ROLE_ALPHA)
        roles.append(ROLE_DOCTOR)
        roles.append(ROLE_SPY)
        werewolves = max(1, (num - 3) // 4)
        villagers = num - (werewolves + 3)
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
        await app.send_message(chat_id, f"🌗 It's now {next_phase.upper()} time!", parse_mode=ParseMode.MARKDOWN)
        if next_phase == "night":
            await night_phase_logic(chat_id, game_id)
        else:
            await day_phase_logic(chat_id, game_id)
        await asyncio.sleep(60)

async def night_phase_logic(chat_id, game_id):
    actions_col.delete_many({"chat_id": chat_id})
    players = list(players_col.find({"game_id": game_id}))
    werewolves = [p for p in players if p.get("role") in [ROLE_WEREWOLF, ROLE_ALPHA]]
    innocents = [p for p in players if p.get("role") in [ROLE_VILLAGER, ROLE_DOCTOR]]

    spy = next((p for p in players if p.get("role") == ROLE_SPY), None)
    if spy:
        spy_id = spy["_id"]
        spy_name = spy.get("name", "Spy")
        spy_once_used = spy.get("spy_once_used", False)
        show_self = not spy_once_used and random.random() < 0.5

        reveal_list = []

        if show_self:
            reveal_list.append(spy)
            players_col.update_one({"_id": spy_id}, {"$set": {"spy_once_used": True}})
        else:
            reveal_list.extend(random.sample(innocents, min(2, len(innocents))))

        other_werewolves = [w for w in werewolves if w.get("role") == ROLE_WEREWOLF]
        if other_werewolves:
            reveal_list.append(random.choice(other_werewolves))

        if len(reveal_list) == 3:
            random.shuffle(reveal_list)
            names = " | ".join([pl.get("name", str(pl["_id"])) for pl in reveal_list])
            await app.send_message(chat_id, f"🕵️ {names}\nSpy {spy_name} confirmed that one of them is a werewolf. Choose your vote wisely.")

    for p in players:
        role = p.get("role")
        uid = p["_id"]
        if role == ROLE_ALPHA:
            await app.send_message(uid, "🩸 Alpha Werewolf: Choose TWO players to bite.", reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(pl.get("name", str(pl["_id"])), callback_data=f"alpha_bite_{pl['_id']}")] for pl in players if pl["_id"] != uid]
            ))
        elif role == ROLE_WEREWOLF:
            targets = [pl for pl in players if pl["_id"] != uid and pl.get("role") not in [ROLE_WEREWOLF, ROLE_ALPHA]]
            await app.send_message(uid, "🌙 Werewolf night: Choose a victim to vote.", reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton(pl.get("name", str(pl["_id"])), callback_data=f"target_wvote_{pl['_id']}")] for pl in targets]
            ))
        elif role == ROLE_DOCTOR:
            await send_dm(uid, "🌙 Night phase: Select a player to heal.", "heal")

async def day_phase_logic(chat_id, game_id):
    actions = list(actions_col.find({"chat_id": chat_id}))
    heals = [a["target_id"] for a in actions if a["action"] == "heal"]
    spys = [a for a in actions if a["action"] == "spy"]
    bites = [a for a in actions if a["action"] == "bite"]
    wvotes = [a["target_id"] for a in actions if a["action"] == "wvote"]

    if wvotes:
        vote_count = {}
        for tid in wvotes:
            vote_count[tid] = vote_count.get(tid, 0) + 1
        max_votes = max(vote_count.values())
        top_targets = [tid for tid, count in vote_count.items() if count == max_votes]

        if len(top_targets) > 1:
            await app.send_message(chat_id, "💥 Villagers kicked off werewolf's plan! Their vote was divided.")
        else:
            victim = int(top_targets[0])
            if victim not in heals:
                target = players_col.find_one({"_id": victim})
                if target:
                    role = target.get("role")
                    players_col.delete_one({"_id": victim})
                    user = await app.get_users(victim)
                    if role == ROLE_ALPHA:
                        await app.send_message(chat_id, f"☠️ A tragedy happened. Alpha {user.first_name} was executed by his own clan!")
                    else:
                        await app.send_message(chat_id, f"☠️ {user.first_name} ({role}) was killed by werewolves last night.")
            else:
                await app.send_message(chat_id, "💉 The doctor saved a life from the werewolves.")
    else:
        await app.send_message(chat_id, "😴 No werewolf attack occurred last night.")

    for bite_group in [bites[i:i+2] for i in range(0, len(bites), 2)]:
        if len(bite_group) == 2:
            target_ids = [int(bite_group[0]["target_id"]), int(bite_group[1]["target_id"])]
            chosen = random.choice(target_ids)
            target = players_col.find_one({"_id": chosen})
            if target and target.get("role") in [ROLE_WEREWOLF, ROLE_ALPHA]:
                players_col.delete_one({"_id": chosen})
                user = await app.get_users(chosen)
                await app.send_message(chat_id, f"💀 Alpha overbite his own clan {user.first_name} led to tragic death.")
            else:
                players_col.update_one({"_id": chosen}, {"$set": {"role": ROLE_WEREWOLF}})
                await app.send_message(chat_id, "🧠 A new mind joined the werewolf side.")

    for spy_action in spys:
        target = players_col.find_one({"_id": spy_action["target_id"]})
        role = target.get("role", "Unknown")
        try:
            await app.send_message(spy_action["user_id"], f"🕵️ You spied on {target.get('name', 'a player')}\n\nRole: {role.capitalize()}")
        except:
            pass

    spy = next((p for p in players_col.find({"game_id": game_id, "role": ROLE_SPY})), None)
    if spy:
        if players_col.count_documents({"game_id": game_id, "role": ROLE_SPY}) == 0:
            await app.send_message(chat_id, "🕵️ You've lost a great ally. The spy is no longer with you.")

    await voting_phase(chat_id, game_id)

async def voting_phase(chat_id, game_id):
    players = list(players_col.find({"game_id": game_id}))
    buttons = [[InlineKeyboardButton(f"{p.get('name', str(p['id']))}", callback_data=f"vote_{p['_id']}")] for p in players]
    buttons.append([InlineKeyboardButton("Skip Vote", callback_data="vote_skip")])
    await app.send_message(chat_id, "🗳️ Day Vote: Choose who to eliminate.", reply_markup=InlineKeyboardMarkup(buttons))
    await asyncio.sleep(60)

    votes = list(actions_col.find({"chat_id": chat_id, "action": "vote"}))
    vote_counts = {}
    for v in votes:
        vote_counts[v["target_id"]] = vote_counts.get(v["target_id"], 0) + 1

    if vote_counts:
        target = max(vote_counts, key=vote_counts.get)
        if target != "skip":
            players_col.delete_one({"_id": int(target)})
            user = await app.get_users(int(target))
            await app.send_message(chat_id, f"⚖️ {user.first_name} was lynched by vote.")
        else:
            await app.send_message(chat_id, "⚖️ No one was lynched today.")
    else:
        await app.send_message(chat_id, "⚖️ No votes received. No one lynched.")

    await check_win_condition(chat_id, game_id)

def count_roles(game_id):
    players = list(players_col.find({"game_id": game_id}))
    role_counts = {ROLE_WEREWOLF: 0, ROLE_ALPHA: 0, ROLE_VILLAGER: 0}
    for p in players:
        role = p.get("role")
        if role in role_counts:
            role_counts[role] += 1
    return role_counts

async def check_win_condition(chat_id, game_id):
    counts = count_roles(game_id)
    if counts[ROLE_WEREWOLF] + counts[ROLE_ALPHA] == 0:
        await app.send_message(chat_id, "🎉 Villagers win! All werewolves eliminated.")
        await reset_game(chat_id)
    elif counts[ROLE_WEREWOLF] + counts[ROLE_ALPHA] >= counts[ROLE_VILLAGER]:
        await app.send_message(chat_id, "🐺 Werewolves win! They outnumber the villagers.")
        await reset_game(chat_id)

async def send_dm(user_id, text, action_type):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Select Target", callback_data=f"action_{action_type}")]
    ])
    try:
        await app.send_message(user_id, text, reply_markup=keyboard)
    except:
        pass

@app.on_callback_query(filters.regex(r"action_(kill|heal|spy)"))
async def action_handler(client, callback):
    action = callback.data.split("_")[1]
    user_id = callback.from_user.id
    player = players_col.find_one({"_id": user_id})
    game_id = player.get("game_id")
    chat_id = player.get("game_chat")
    others = list(players_col.find({"game_id": game_id, "_id": {"$ne": user_id}}))
    buttons = [[InlineKeyboardButton(p.get("name", str(p["_id"])), callback_data=f"target_{action}_{p['_id']}")] for p in others]
    await callback.message.edit_text("Select your target:", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex(r"target_(kill|heal|spy|vote)_(\d+)"))
async def target_handler(client, callback):
    _, action, target_id = callback.data.split("_")
    user_id = callback.from_user.id
    player = players_col.find_one({"_id": user_id})
    chat_id = player.get("game_chat")
    existing = actions_col.find_one({"chat_id": chat_id, "user_id": user_id, "action": action})
    if existing:
        actions_col.update_one({"_id": existing["_id"]}, {"$set": {"target_id": target_id}})
    else:
        actions_col.insert_one({"chat_id": chat_id, "user_id": user_id, "action": action, "target_id": target_id})
    await callback.answer("✅ Action submitted.", show_alert=True)
    await callback.message.delete()

@app.on_callback_query(filters.regex(r"target_wvote_(\d+)"))
async def werewolf_vote_handler(client, callback):
    user_id = callback.from_user.id
    target_id = int(callback.data.split("_")[2])
    player = players_col.find_one({"_id": user_id})
    chat_id = player.get("game_chat")
    existing = actions_col.find_one({"chat_id": chat_id, "user_id": user_id, "action": "wvote"})
    if existing:
        actions_col.update_one({"_id": existing["_id"]}, {"$set": {"target_id": target_id}})
    else:
        actions_col.insert_one({"chat_id": chat_id, "user_id": user_id, "action": "wvote", "target_id": target_id})
    await callback.answer("✅ Vote cast.", show_alert=True)
    await callback.message.delete()

@app.on_callback_query(filters.regex(r"alpha_bite_(\d+)"))
async def alpha_bite_handler(client, callback):
    user_id = callback.from_user.id
    target_id = int(callback.data.split("_")[2])
    player = players_col.find_one({"_id": user_id})
    chat_id = player.get("game_chat")
    existing = actions_col.count_documents({"chat_id": chat_id, "user_id": user_id, "action": "bite"})
    if existing < 2:
        actions_col.insert_one({"chat_id": chat_id, "user_id": user_id, "action": "bite", "target_id": target_id})
        await callback.answer("✅ Bite target selected.", show_alert=True)
    else:
        await callback.answer("❌ You have already selected 2 targets.", show_alert=True)
    await callback.message.delete()

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
        players_col.update_one({"_id": pid}, {"$set": {"role": role, "game_id": game_id, "game_chat": chat_id, "disguised": False, "healed_times": 0}}, upsert=True)

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



