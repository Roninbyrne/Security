from pyrogram import Client, filters
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
db = mongo_client.security
settings_collection = db.settings

def generate_security_code():
    parts = [''.join(random.choices(string.ascii_lowercase + string.digits, k=4)) for _ in range(4)]
    return '-'.join(parts)

@app.on_message(filters.private & filters.command("newsecurity"))
async def new_security(client: Client, message: Message):
    await message.reply("Send the username of the log channel (e.g., @yourchannel):")
    response = await client.listen(message.chat.id)
    channel_username = response.text.strip()
    security_code = generate_security_code()
    settings_collection.insert_one({
        "security_code": security_code,
        "security_owner": message.from_user.id,
        "log_channel": channel_username,
        "linked_groups": [],
        "copyright_protection": False,
        "link_security": False,
        "spam": False,
        "words_limitations": False
    })
    await message.reply(f"Security code generated:\n\n`{security_code}`")

@app.on_message(filters.group & filters.command("securegc"))
async def secure_group(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply("Please provide your security code.\nUsage: `/securegc <code>`")
    security_code = message.command[1].strip()
    security_data = settings_collection.find_one({"security_code": security_code})
    if not security_data:
        return await message.reply("Invalid security code.")

    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if member.status != "owner":
            return await message.reply("Only the group owner can activate security.")
    except:
        return await message.reply("Could not verify ownership.")

    settings_collection.update_one(
        {"security_code": security_code},
        {
            "$addToSet": {"linked_groups": message.chat.id},
            "$set": {"group_id": message.chat.id}
        }
    )

    buttons = [
        [
            InlineKeyboardButton(
                f"Copyright Protection 🔒",
                callback_data=f"toggle:{security_code}:copyright_protection"
            )
        ],
        [
            InlineKeyboardButton(
                f"LINK Security 🔒",
                callback_data=f"toggle:{security_code}:link_security"
            )
        ],
        [
            InlineKeyboardButton(
                f"Spam 🔒",
                callback_data=f"toggle:{security_code}:spam"
            )
        ],
        [
            InlineKeyboardButton(
                f"Words Limitations 🔒",
                callback_data=f"toggle:{security_code}:words_limitations"
            )
        ]
    ]

    await message.reply("Choose the security level:", reply_markup=InlineKeyboardMarkup(buttons))