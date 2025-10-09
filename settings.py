import os
from pathlib import Path

from dotenv import load_dotenv
import telebot
from openai import OpenAI

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover - redis is optional in some environments
    redis = None

# Загружаем переменные из .env рядом с файлом
load_dotenv(Path(__file__).resolve().parent / ".env")

TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- Redis configuration ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

# --- Новые настройки моделей для мультимедиа ---
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-1")     # генерация изображений (минимальная стоимость)
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o-mini")   # анализ изображений (vision)

# --- Модель для основного чата (GPT-5 mini) ---
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-5-mini")

# ID владельца бота (без ограничений)
OWNER_ID = 1308643253


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

# Maximum number of conversation messages to retain per user
HISTORY_LIMIT = 700  # Храним переписку за неделю (~100 сообщений в день × 7 дней)

# System prompt for the GPT assistant
SYSTEM_PROMPT = (
    "Ты — SynteraGPT. "
    "Работай как универсальный собеседник и следуй инструкциям, которые будут заданы ниже в зависимости от режима или тарифа."
)

if not TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден в .env")
if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY не найден в .env")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

client = OpenAI(api_key=OPENAI_API_KEY)


def _init_redis_client():
    if redis is None:
        return None

    connection_kwargs = {
        "host": REDIS_HOST,
        "port": REDIS_PORT,
        "db": REDIS_DB,
        "decode_responses": True,
    }
    if REDIS_PASSWORD:
        connection_kwargs["password"] = REDIS_PASSWORD

    try:
        client = redis.Redis(**connection_kwargs)
        client.ping()
        return client
    except redis.RedisError:
        return None


r = _init_redis_client()

# Explicit re-exports for clearer "from settings import ..." usage
__all__ = [
    "bot",
    "client",
    "r",
    "SYSTEM_PROMPT",
    "OWNER_ID",
    "is_owner",
    "HISTORY_LIMIT",
    "IMAGE_MODEL",
    "VISION_MODEL",
    "CHAT_MODEL",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_DB",
    "REDIS_PASSWORD",
]
