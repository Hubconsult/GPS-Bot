import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TOKEN = BOT_TOKEN  # 👈 добавляем TOKEN, чтобы bot.py его видел

if not TOKEN:
    raise ValueError("❌ Ошибка: переменная BOT_TOKEN не найдена. Проверь .env файл!")

FREE_LIMIT = 10
PAY_BUTTON_URL = "https://yookassa.ru/"
CONSULT_LINK = "https://t.me/HubConsult"
