"""Centralised configuration for the Telegram bot.

This module loads required credentials from environment variables and
instantiates the :class:`telebot.TeleBot` and OpenAI client instances used
throughout the project.  Importing this module has side effects (creating the
clients) which is acceptable here because both objects are effectively single
tons for the application lifecycle.
"""

import os

from dotenv import load_dotenv
import telebot
from openai import OpenAI


# Load variables from .env
load_dotenv()


# Configuration values used by bot.py
# They can be overridden via environment variables or a .env file
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FREE_LIMIT = int(os.getenv("FREE_LIMIT", "10"))
PAY_BUTTON_URL = os.getenv("PAY_BUTTON_URL", "https://yookassa.ru/")

# Ensure required credentials are provided
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env — проверь файл .env в корне проекта")
if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY не найден в .env")


# Instantiate shared clients
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
client = OpenAI(api_key=OPENAI_API_KEY)


