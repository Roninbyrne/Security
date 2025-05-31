from Security import app  
from pyrogram import filters  
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton  
from Security.plugins.tools.db import players_col, actions_col, games_col  
from bson import ObjectId  
  
@app.on_callback_query(filters.regex(r"action_(kill|heal|spy)"))  
async def action_handler(client, callback):  
    action = callback.data.split("_")[1]  
    user_id = callback.from_user.id  
    player = players_col.find_one({"_id": user_id})  
    game_id = player.get("game_id")  
    others = list(players_col.find({"game_id": game_id, "_id": {"$ne": user_id}}))  
    buttons = [[InlineKeyboardButton(p.get("name", str(p["_id"])), callback_data=f"target_{action}_{p['_id']}")] for p in others]  
    await callback.message.edit_text("Select your target:", reply_markup=InlineKeyboardMarkup(buttons))  
  
@app.on_callback_query(filters.regex(r"target_(kill|heal|spy|vote)_(\\d+)"))  
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
  
@app.on_callback_query(filters.regex(r"target_wvote_(\\d+)"))  
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
  
@app.on_callback_query(filters.regex(r"alpha_bite_(\\d+)"))  
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
  
@app.on_callback_query(filters.regex(r"join_"))  
async def join_game(client, callback):  
    user_id = callback.from_user.id  
    game_id = callback.data.split("_")[1]  
    game_id = ObjectId(game_id)  
    game = games_col.find_one({"_id": game_id})  
    if not game or not game.get("active") or game.get("phase") != "lobby":  
        await callback.answer("❌ Not accepting joins.", show_alert=True)  
        return  
    players = game.get("players", [])  
    if user_id in players:  
        await callback.answer("✅ Already joined.")  
        return  
    if len(players) >= 16:  
        await callback.answer("❌ Game full.")  
        return  
    players.append(user_id)  
    games_col.update_one({"_id": game_id}, {"$set": {"players": players}})  
    await callback.answer(f"✅ Joined! Total: {len(players)}")  
  
@app.on_callback_query(filters.regex(r"reveal_"))  
async def reveal_role(client, callback):  
    user_id = callback.from_user.id  
    game_id = callback.data.split("_")[1]  
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
    await callback.message.edit_text(text, parse_mode="Markdown")  

@app.on_callback_query(filters.regex(r"bulkrole_"))
async def bulkrole_handler(client, callback):
    user_id = callback.from_user.id
    game_id = callback.data.split("_")[1]
    game_id = ObjectId(game_id)

    player = players_col.find_one({"_id": user_id, "game_id": game_id})
    if not player:
        await callback.answer("❌ You are not part of this game.", show_alert=True)
        return

    role = player.get("role", "Unknown").capitalize()
    disguised = player.get("disguised", False)
    text = f"🎭 Role: *{role}*\n"
    if disguised:
        text += "🕵️‍♂️ You are currently disguised."

    await callback.answer()
    await callback.message.edit_text(text, parse_mode="Markdown")
