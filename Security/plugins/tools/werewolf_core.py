from Security import app
from Security.plugins.tools.db import games_col, players_col, actions_col
from Security.plugins.tools.config import ROLE_WEREWOLF, ROLE_VILLAGER, ROLE_ALPHA, ROLE_DOCTOR, ROLE_SPY
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
import random
import asyncio

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

async def send_dm(user_id, text, action_type):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Select Target", callback_data=f"action_{action_type}")]
    ])
    try:
        await app.send_message(user_id, text, reply_markup=keyboard)
    except:
        pass