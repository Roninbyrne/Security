from pyrogram import Client, filters
from Yumi import app
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
import asyncio
from config import MONGO_DB_URI, Helpers

mongo_client = MongoClient(MONGO_DB_URI)
db = mongo_client['my_bot_db']
user_states_collection = db['user_states']
video_channels_collection = db['video_channels']

@app.on_message(filters.command("upload") & filters.private)
def upload_video(client, message):
    user_id = message.chat.id
    if user_id not in Helpers:
        client.send_message(user_id, "❌ You do not have permission to use this command.")
        return

    try:
        command_params = message.text.split(" ")
        public_channel = command_params[1]
        private_channel = command_params[2]
    except IndexError:
        client.send_message(message.chat.id, "Usage: /upload <public_channel> <private_channel>")
        return

    user_states_collection.update_one(
        {"user_id": message.chat.id},
        {"$set": {
            "step": "get_video_link",
            "public_channel": public_channel,
            "private_channel": private_channel
        }},
        upsert=True
    )
    client.send_message(message.chat.id, "Please send the video message link.")

@app.on_message(filters.private)
def handle_messages(client, message):
    user_id = message.chat.id
    user_state = user_states_collection.find_one({"user_id": user_id})

    if user_state:
        state = user_state.get("step")

        if state == "get_video_link":
            get_video_link(client, message)
        elif state == "get_description":
            get_description(client, message)
        elif state == "get_cover_photo":
            get_cover_photo(client, message)

def get_video_link(client, message):
    video_link = message.text
    user_states_collection.update_one(
        {"user_id": message.chat.id},
        {"$set": {"video_link": video_link, "step": "get_description"}}
    )
    client.send_message(message.chat.id, "Please provide a description.")

def get_description(client, message):
    description = message.text
    user_states_collection.update_one(
        {"user_id": message.chat.id},
        {"$set": {"description": description, "step": "get_cover_photo"}}
    )
    client.send_message(message.chat.id, "Please send the cover photo.")

def get_cover_photo(client, message):
    if message.photo:
        cover_photo = message.photo.file_id
        user_state = user_states_collection.find_one({"user_id": message.chat.id})

        video_link = user_state.get("video_link")
        description = user_state.get("description")
        public_channel = user_state.get("public_channel")
        private_channel = user_state.get("private_channel")

        video_id = video_link.split('/')[-1]
        post_video_to_channel(public_channel, video_id, description, cover_photo)

        video_channels_collection.update_one(
            {"video_id": video_id},
            {"$set": {
                "public_channel": public_channel,
                "private_channel": private_channel
            }},
            upsert=True
        )

        client.send_message(message.chat.id, "Video details uploaded to the public channel!")

def post_video_to_channel(public_channel, video_id, description, cover_photo):
    button = InlineKeyboardMarkup([[InlineKeyboardButton("✯ ᴅᴏᴡɴʟᴏᴀᴅ ✯", callback_data=video_id)]])

    app.send_photo(
        chat_id=public_channel,
        photo=cover_photo,
        caption=f"{description}\n\n❱ ꜱᴜᴘᴘᴏʀᴛ ᴄʜᴀᴛ<a href='https://t.me/phoenixXsupport'> [ ᴄʟɪᴄᴋ ʜᴇʀᴇ ]</a>",
        reply_markup=button
    )

@app.on_callback_query()
async def handle_button_click(client, callback_query):
    video_id = callback_query.data
    user_id = callback_query.from_user.id

    video_info = video_channels_collection.find_one({"video_id": video_id})

    if not video_info:
        await callback_query.answer("Video not found. Please try uploading again.", show_alert=True)
        return

    private_channel = video_info["private_channel"]

    try:
        message = await client.get_messages(private_channel, int(video_id))
        if message:
            if message.video:
                file_id = message.video.file_id
                sent_message = await client.send_video(user_id, file_id)
            elif message.document:
                file_id = message.document.file_id
                sent_message = await client.send_document(user_id, file_id)

            await callback_query.answer("ꜰᴇᴛᴄʜɪɴɢ ʏᴏᴜʀ ʀᴇQᴜᴇꜱᴛ.... ᴘʟᴇᴀꜱᴇ ᴄʜᴇᴄᴋ ʙᴏᴛ 𝗬ᴜᴍɪ 花 子 ᴅᴍ", show_alert=True)
            await client.send_message(user_id, "ᴘʟᴇᴀꜱᴇ ꜰᴏʀᴡᴀʀᴅ ᴛʜɪꜱ ᴠɪᴅᴇᴏ ᴏʀ ꜰɪʟᴇ ɪɴ ʏᴏᴜʀ ꜱᴀᴠᴇᴅ ᴍᴇꜱꜱᴀɢᴇꜱ ᴀɴᴅ ᴅᴏᴡɴʟᴏᴀᴅ ᴛʜᴇʀᴇ, ᴛʜᴇ ᴄᴏɴᴛᴇɴᴛ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ᴀꜰᴛᴇʀ 5 ᴍɪɴᴜᴛᴇꜱ .")
            await asyncio.sleep(300)
            await client.delete_messages(user_id, sent_message.id)
        else:
            await callback_query.answer("ᴄᴏɴᴛᴇɴᴛ ɴᴏᴛ ꜰᴏᴜɴᴅ ᴏʀ ɪᴛꜱ ɴᴏᴛ ᴀ ᴠɪᴅᴇᴏ ᴏʀ ꜰɪʟᴇ ᴍᴇꜱꜱᴀɢᴇ.", show_alert=True)
    except Exception as e:
        await callback_query.answer("ꜰᴀɪʟᴇᴅ ᴛᴏ ʀᴇᴛʀɪᴇᴠᴇ ᴄᴏɴᴛᴇɴᴛ, ᴘʟᴇᴀꜱᴇ ᴛʏᴘᴇ /start ᴏɴ ʙᴏᴛ 𝗬ᴜᴍɪ 花 子 ᴅᴍ.", show_alert=True)
        print(f"Error fetching content: {e}")

if __name__ == "__main__":
    app.run()