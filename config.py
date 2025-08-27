# config.py

import os
from dotenv import load_dotenv

load_dotenv()  # загружает переменные из .env

# токен нового бота от BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOKEN = BOT_TOKEN  # 👈 добавляем алиас для совместимости с bot.py

if not TOKEN:
    raise ValueError("❌ Ошибка: переменная BOT_TOKEN не найдена. Проверь .env файл!")

# лимит бесплатных сообщений
FREE_LIMIT = 10  

# ссылка на оплату (пока заглушка для ЮKassa)
PAY_BUTTON_URL = "https://yookassa.ru/"

# (необязательно, но можно оставить)
CONSULT_LINK = "https://t.me/HubConsult"
