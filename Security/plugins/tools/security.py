from pyrogram import Client, filters
from pyrogram.types import Message
from Security import app
from pymongo import MongoClient
from config import MONGO_DB_URI, OWNER_ID
from datetime import datetime, timedelta
import random

mongo_client = MongoClient(MONGO_DB_URI)
db = mongo_client.security
settings_collection = db.settings
security_col = db.security

MUTE_TIMES = [60, 120, 300, 600, 900, 1800]

@app.on_message(filters.group)
async def enforce_security(client: Client, message: Message):
    if not message.from_user:
        return

    user_id = message.from_user.id
    group_id = message.chat.id

    security_data = security_col.find_one({"linked_groups": group_id})
    if not security_data:
        return

    security_code = security_data["security_code"]
    settings = settings_collection.find_one({"security_code": security_code}) or {}

    if user_id == security_data.get("owner_id") or user_id == OWNER_ID:
        return

    # Copyright Protection: delete edited messages
    if settings.get("copyright_protection") and message.edit_date:
        await message.delete()
        await take_action(client, message, group_id, user_id, "Copyright Edit Detected")
        return

    # Link Security
    if settings.get("link_security") and ("t.me/" in message.text.lower() or "http" in message.text.lower()):
        await message.delete()
        await take_action(client, message, group_id, user_id, "Link Sharing")
        return

    # Spam Protection
    if settings.get("spam"):
        if hasattr(message, "text") and len(set(message.text.lower().split())) <= 3:
            await message.delete()
            await take_action(client, message, group_id, user_id, "Spam Detected")
            return

    # Word Limitation
    if settings.get("words_limitations") and message.text and len(message.text.split()) > 150:
        await message.delete()
        await mute_user(client, group_id, user_id, message)

async def take_action(client, message, group_id, user_id, reason):
    duration = random.choice(MUTE_TIMES)
    until_date = datetime.utcnow() + timedelta(seconds=duration)

    await client.restrict_chat_member(group_id, user_id, permissions=None, until_date=until_date)

    user_mention = message.from_user.mention if message.from_user else str(user_id)
    await message.reply(f"{user_mention} has been muted for {reason}. Duration: {duration // 60} minutes")

    security_data = security_col.find_one({"linked_groups": group_id})
    if not security_data:
        return

    log_channel = security_data.get("log_channel")
    if not log_channel:
        return

    text = f"Group: {message.chat.title}\nChat ID: {group_id}\nUser: {user_mention}\nUserID: {user_id}\nUsername: @{message.from_user.username if message.from_user.username else '-'}\nReason: {reason}\nAction: Mute {duration // 60} minutes"

    try:
        await client.send_message(log_channel, text)
    except:
        pass

async def mute_user(client, group_id, user_id, message):
    reason = "Message too long"
    await take_action(client, message, group_id, user_id, reason)