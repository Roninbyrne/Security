from pyrogram import Client
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from Security import app
from config import OWNER_ID, MONGO_DB_URI
from pymongo import MongoClient

mongo_client = MongoClient(MONGO_DB_URI)
db = mongo_client['SecurityBot']
security_col = db['security']

@app.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    if "|" not in data:
        return

    setting_type, group_id = data.split("|")
    group_id = int(group_id)

    security_data = security_col.find_one({"linked_groups": group_id})
    if not security_data:
        await callback_query.answer("Security not set up.", show_alert=True)
        return

    owner_id = security_data.get("owner_id")
    if user_id != owner_id and user_id != OWNER_ID:
        await callback_query.answer("Not authorized.", show_alert=True)
        return

    current_value = security_data.get(setting_type, False)
    new_value = not current_value

    security_col.update_one(
        {"linked_groups": group_id},
        {"$set": {setting_type: new_value}}
    )

    updated_data = security_col.find_one({"linked_groups": group_id})

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"Copyright protection {'🔓' if updated_data.get('copyright', False) else '🔒'}",
                callback_data=f"copyright|{group_id}"
            ),
            InlineKeyboardButton(
                f