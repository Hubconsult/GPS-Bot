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
PAY_URL_HARMONY = os.getenv("PAY_URL_HARMONY", "https://yookassa.ru/")
PAY_URL_REFLECTION = os.getenv("PAY_URL_REFLECTION", "https://yookassa.ru/")
PAY_URL_TRAVEL = os.getenv("PAY_URL_TRAVEL", "https://yookassa.ru/")

# --- Новые настройки моделей для мультимедиа ---
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-1")     # генерация изображений
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o-mini")   # анализ изображений (vision)

# --- Урлы для докупки пакетов (можно оставить заглушки) ---
PAY_URL_PACK_PHOTO_50 = os.getenv("PAY_URL_PACK_PHOTO_50", "https://yookassa.ru/")
PAY_URL_PACK_PHOTO_200 = os.getenv("PAY_URL_PACK_PHOTO_200", "https://yookassa.ru/")
PAY_URL_PACK_DOC_10 = os.getenv("PAY_URL_PACK_DOC_10", "https://yookassa.ru/")
PAY_URL_PACK_DOC_30 = os.getenv("PAY_URL_PACK_DOC_30", "https://yookassa.ru/")
PAY_URL_PACK_ANALYZE_20 = os.getenv("PAY_URL_PACK_ANALYZE_20", "https://yookassa.ru/")
PAY_URL_PACK_ANALYZE_100 = os.getenv("PAY_URL_PACK_ANALYZE_100", "https://yookassa.ru/")

# ID владельца бота (без ограничений)
OWNER_ID = 1308643253


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

# Maximum number of conversation messages to retain per user
HISTORY_LIMIT = 15

# System prompt for the GPT assistant
SYSTEM_PROMPT = (
    "Ты — GPT-5 mini. "
    "Работай как универсальный собеседник и следуй инструкциям, которые будут заданы ниже в зависимости от режима или тарифа."
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
    "PAY_URL_HARMONY",
    "PAY_URL_REFLECTION",
    "PAY_URL_TRAVEL",
    "SYSTEM_PROMPT",
    "OWNER_ID",
    "is_owner",
    "HISTORY_LIMIT",
]

__all__ += [
    "IMAGE_MODEL",
    "VISION_MODEL",
    "PAY_URL_PACK_PHOTO_50",
    "PAY_URL_PACK_PHOTO_200",
    "PAY_URL_PACK_DOC_10",
    "PAY_URL_PACK_DOC_30",
    "PAY_URL_PACK_ANALYZE_20",
    "PAY_URL_PACK_ANALYZE_100",
]

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_API_KEY = os.getenv("YOOKASSA_API_KEY")

__all__ += ["YOOKASSA_SHOP_ID", "YOOKASSA_API_KEY"]
