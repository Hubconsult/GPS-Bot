import os
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

# Configuration values used by bot.py
TOKEN = os.getenv("BOT_TOKEN")
FREE_LIMIT = 10
PAY_BUTTON_URL = "https://yookassa.ru/"

# Ensure the bot token is provided
if not TOKEN:
    raise ValueError(
        "❌ BOT_TOKEN не найден в .env — проверь файл .env в корне проекта"
    )

