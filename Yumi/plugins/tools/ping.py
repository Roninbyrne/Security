from pyrogram import Client, filters
import psutil
import time
from datetime import timedelta
import logging
from Yumi import app
from config import PING_IMG_URL

bot_start_time = time.time()

@app.on_message(filters.command(["ping", "alive"]))
async def ping(client, message):
    try:
        uptime_seconds = time.time() - bot_start_time
        uptime = str(timedelta(seconds=int(uptime_seconds)))

        ram = psutil.virtual_memory()
        ram_usage = f"{ram.percent}% ᴜꜱᴇᴅ ({ram.used / (1024 ** 3):.2f} ɢʙ ᴏꜰ {ram.total / (1024 ** 3):.2f} ɢʙ)"
        cpu_usage = f"{psutil.cpu_percent(interval=1)}%"
        disk = psutil.disk_usage('/')
        disk_usage = f"{disk.percent}% ᴜꜱᴇᴅ ({disk.used / (1024 ** 3):.2f} ɢʙ ᴏꜰ {disk.total / (1024 ** 3):.2f} ɢʙ)"

        # Merge the image and stats into one message
        stats_message = (
            f"↬ sʏsᴛᴇᴍ sᴛᴀᴛs : <a href='{PING_IMG_URL}'> </a>\n\n"
            f"↬ ᴜᴩᴛɪᴍᴇ : {uptime}\n"
            f"↬ ᴄᴩᴜ : {cpu_usage}\n"
            f"↬ ʀᴀᴍ : {ram_usage}\n"
            f"↬ ᴅɪsᴋ : {disk_usage}\n"
        )

        await message.reply(stats_message)

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        error_message = "An error occurred while retrieving system stats."
        await message.reply(error_message)