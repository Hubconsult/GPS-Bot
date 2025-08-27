import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

# Токен Telegram-бота
TOKEN = os.getenv("BOT_TOKEN")

# Лимит бесплатных диалогов
FREE_LIMIT = 10  

# Ссылка на оплату (замени на свою, если нужно)
PAY_BUTTON_URL = "https://yookassa.ru/"

# Проверка на случай ошибки
if not TOKEN:
    raise ValueError("❌ Ошибка: BOT_TOKEN не найден в .env!")
