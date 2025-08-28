import os
from dotenv import load_dotenv
import telebot
from openai import OpenAI

# Загружаем переменные из .env
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FREE_LIMIT = int(os.getenv("FREE_LIMIT", "10"))
PAY_BUTTON_URL = os.getenv("PAY_BUTTON_URL", "https://yookassa.ru/")

if not TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env")
if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY не найден в .env")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
client = OpenAI(api_key=OPENAI_API_KEY)

# Explicit re-exports for clearer "from settings import ..." usage
__all__ = ["bot", "client", "FREE_LIMIT", "PAY_BUTTON_URL"]
