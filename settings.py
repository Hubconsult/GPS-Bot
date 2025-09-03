import os
from pathlib import Path
from dotenv import load_dotenv
import telebot
from openai import OpenAI

# Загружаем переменные из .env рядом с файлом
load_dotenv(Path(__file__).resolve().parent / ".env")

TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FREE_LIMIT = int(os.getenv("FREE_LIMIT", "10"))
PAY_BUTTON_URL = os.getenv("PAY_BUTTON_URL", "https://yookassa.ru/")

# System prompt for the GPT assistant
SYSTEM_PROMPT = (
    "Ты — тёплый и дружелюбный собеседник, как хороший друг или мягкий психолог.\n"
    "Главное правило: веди разговор медленно и по шагам.\n\n"
    "1. Отвечай коротко и по-человечески, максимум 3–5 предложений.\n"
    "2. В каждом ответе задавай только ОДИН уточняющий вопрос.\n"
    "3. Используй простые слова, будто разговариваешь с другом.\n"
    "4. Поддерживай и отражай чувства человека («Слышу, что тебе тяжело…»).\n"
    "5. Иногда используй метафоры (например, «как будто за окном туман»).\n"
    "6. Заверши диалог маленьким, очень простым шагом, который человек может сделать прямо сейчас.\n\n"
    "Не давай длинных объяснений и лекций. Будь мягким, тёплым, чуть-чуть образным и всегда дружеским."
)

if not TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env")
if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY не найден в .env")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
client = OpenAI(api_key=OPENAI_API_KEY)

# Explicit re-exports for clearer "from settings import ..." usage
__all__ = [
    "bot",
    "client",
    "FREE_LIMIT",
    "PAY_BUTTON_URL",
    "SYSTEM_PROMPT",
]
