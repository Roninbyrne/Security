from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from Security import app
from config import OWNER_ID
from pymongo import MongoClient
from datetime import datetime
import random
import string

from Security.plugins.tools.callback import *
from Security.plugins.tools.security import *

mongo_client = MongoClient(MONGO_DB_URI)
db = mongo_client['SecurityBot']
users_col = db['users']
security_col = db['security']

def generate_security_code():
    parts = []
    for _ in range(4):
        part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        parts.append(part)
    return '-'.join(parts)

@app.on_message(filters.private & filters.command("newsecurity"))
async def create_security(client, message: Message):
    user_id = message.from_user.id
    await message.reply("Send the username of the log channel:")
    
    response = await app.listen(user_id)
    if not response.text.startswith("@"): 
        await message.reply("Invalid channel username. It must start with @")
        return

    log_channel = response.text
    code = generate_security_code()
    
    security_col.insert_one({
        "owner_id": user_id,
        "security_code": code,
        "log_channel": log_channel,
        "linked_groups": []
    })
    
    await message.reply(f"Security created. Use this code in your group:\n`/securegc {code}`")

@app.on_message(filters.group & filters.command("securegc"))
async def secure_group(client, message: Message):
    if not message.from_user:
        return

    user_id = message.from_user.id
    group_id = message.chat.id
    code_parts = message.text.split()

    if len(code_parts) != 2:
        await message.reply("Usage: /securegc <security-code>")
        return

    code = code_parts[1]
    security_data = security_col.find_one({"security_code": code})

    if not security_data:
        await message.reply("Invalid security code.")
        return

    member = await app.get_chat_member(group_id, user_id)
    if member.status != "creator":
        await message.reply("Only group owner can secure the group.")
        return

    security_col.update_one({"security_code": code}, {"$addToSet": {"linked_groups": group_id}})

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Copyright protection 🔒", callback_data=f"copyright_off|{group_id}"),
            InlineKeyboardButton("LINK Security 🔒", callback_data=f"link_off|{group_id}")
        ],
        [
            InlineKeyboardButton("Spam 🔒", callback_data=f"spam_off|{group_id}"),
            InlineKeyboardButton("Words limitations 🔒", callback_data=f"words_off|{group_id}")
        ]
    ])

    await message.reply("Choose the security level:", reply_markup=keyboard)
