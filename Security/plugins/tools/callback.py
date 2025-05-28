from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus
from Security import app
from config import OWNER_ID
from pymongo import MongoClient
from config import MONGO_DB_URI

mongo_client = MongoClient(MONGO_DB_URI)
db = mongo_client.security
settings_collection = db.settings
security_col = db.security

@app.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    if not data.startswith("toggle:"):
        return

    _, security_code, setting_type = data.split(":")
    group_data = settings_collection.find_one({"security_code": security_code})
    link_data = security_col.find_one({"security_code": security_code})

    if not group_data or not link_data:
        return await callback_query.answer("Security settings not found.", show_alert=True)

    group_id = None
    for gid in link_data.get("linked_groups", []):
        try:
            member = await client.get_chat_member(gid, user_id)
            if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
                group_id = gid
                break
        except:
            continue

    if user_id != group_data.get("security_owner") and user_id != group_data.get("group_owner") and user_id != OWNER_ID:
        if group_id:
            member = await client.get_chat_member(group_id, user_id)
            if member.status != ChatMemberStatus.OWNER:
                return await callback_query.answer("You are not allowed to change these settings.", show_alert=True)
        else:
            return await callback_query.answer("You are not allowed to change these settings.", show_alert=True)

    current_value = group_data.get(setting_type, False)
    new_value = not current_value

    settings_collection.update_one(
        {"security_code": security_code},
        {"$set": {setting_type: new_value}}
    )

    updated_data = settings_collection.find_one({"security_code": security_code})

    await callback_query.answer(
        f"{setting_type.replace('_', ' ').title()} {'enabled' if new_value else 'disabled'}.",
        show_alert=True
    )

    buttons = [
        [
            InlineKeyboardButton(
                f"Copyright Protection {'🔓' if updated_data.get('copyright_protection', False) else '🔒'}",
                callback_data=f"toggle:{security_code}:copyright_protection"
            )
        ],
        [
            InlineKeyboardButton(
                f"LINK Security {'🔓' if updated_data.get('link_security', False) else '🔒'}",
                callback_data=f"toggle:{security_code}:link_security"
            )
        ],
        [
            InlineKeyboardButton(
                f"Spam {'🔓' if updated_data.get('spam', False) else '🔒'}",
                callback_data=f"toggle:{security_code}:spam"
            )
        ],
        [
            InlineKeyboardButton(
                f"Words Limitations {'🔓' if updated_data.get('words_limitations', False) else '🔒'}",
                callback_data=f"toggle:{security_code}:words_limitations"
            )
        ]
    ]

    await callback_query.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(buttons)
    )