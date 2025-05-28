from pyrogram import Client, filters
from Security import app
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from datetime import datetime, timedelta
import asyncio
import time
import logging
from config import MONGO_DB_URI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mongo_client = MongoClient(MONGO_DB_URI)
