import os
from pathlib import Path

from contextlib import suppress

from dotenv import load_dotenv
import telebot
from telebot import types
from openai import OpenAI

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover - redis is optional in some environments
    redis = None

# Загружаем переменные из .env рядом с файлом
load_dotenv(Path(__file__).resolve().parent / ".env")

TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PAY_URL_HARMONY = os.getenv("PAY_URL_HARMONY")
PAY_URL_REFLECTION = os.getenv("PAY_URL_REFLECTION")
PAY_URL_TRAVEL = os.getenv("PAY_URL_TRAVEL")

# --- Redis configuration ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

# --- CRM access code ---
CRM_TARIFF_CODE = os.getenv("CRM_TARIFF_CODE", "Syntera GPT 5")

# --- Новые настройки моделей для мультимедиа ---
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "dall-e-3")        # генерация изображений (DALL·E 3 Standard)
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o-mini")   # анализ изображений (vision)

# --- Модель для основного чата (GPT-5 mini) ---
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-5-mini")

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
if not PAY_URL_HARMONY:
    raise ValueError("❌ PAY_URL_HARMONY не найден в .env")
if not PAY_URL_REFLECTION:
    raise ValueError("❌ PAY_URL_REFLECTION не найден в .env")
if not PAY_URL_TRAVEL:
    raise ValueError("❌ PAY_URL_TRAVEL не найден в .env")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# По требованиям заказчика полностью убираем боковое меню со слеш-командами.
# Для этого удаляем зарегистрированные команды и сбрасываем кнопку меню
# (когда команд нет, Telegram больше не показывает боковую кнопку).
with suppress(Exception):
    bot.delete_my_commands()
with suppress(Exception):
    bot.set_chat_menu_button(menu_button=types.MenuButtonDefault())

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
    "CHAT_MODEL",
    "REDIS_HOST",
    "REDIS_PORT",
    "REDIS_DB",
    "REDIS_PASSWORD",
    "CRM_TARIFF_CODE",
    "PAY_URL_PACK_PHOTO_50",
    "PAY_URL_PACK_PHOTO_200",
    "PAY_URL_PACK_DOC_10",
    "PAY_URL_PACK_DOC_30",
    "PAY_URL_PACK_ANALYZE_20",
    "PAY_URL_PACK_ANALYZE_100",
]

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_API_KEY = os.getenv("YOOKASSA_API_KEY")

if not YOOKASSA_SHOP_ID:
    raise ValueError("❌ YOOKASSA_SHOP_ID не найден в .env")
if not YOOKASSA_API_KEY:
    raise ValueError("❌ YOOKASSA_API_KEY не найден в .env")

__all__ += ["YOOKASSA_SHOP_ID", "YOOKASSA_API_KEY"]
