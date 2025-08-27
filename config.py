import os
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOKEN = BOT_TOKEN  # 👈 именно это ждёт bot.py

if not TOKEN:
    raise ValueError("❌ Ошибка: переменная BOT_TOKEN не найдена. Проверь .env файл!")

# Лимит бесплатных диалогов
FREE_LIMIT = 10  

# Ссылка на оплату (пока заглушка)
PAY_BUTTON_URL = "https://yookassa.ru/"

# (опционально)
CONSULT_LINK = "https://t.me/HubConsult"
