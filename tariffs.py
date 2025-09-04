# tariffs.py
from rewards import give_smile, give_avatar, give_next_card
from settings import PAY_URL_HARMONY, PAY_URL_REFLECTION, PAY_URL_TRAVEL
import datetime

# --- Хранилище активных подписок ---
user_tariffs = {}  # {chat_id: {"tariff": str, "start": date, "end": date}}

# --- Тарифы ---
TARIFFS = {
    "sozvuchie": {
        "name": "🌱 Созвучие",
        "price": 299,
        "description": "Первое прикосновение к себе: смайлы и GPT-5 Mini.",
        "starter_reward": give_smile,
        "category": "smiles",
        "pay_url": PAY_URL_HARMONY,
    },
    "otrazhenie": {
        "name": "🌿 Отражение",
        "price": 999,
        "description": "Видеть себя яснее: аватарки и GPT-5 обычный.",
        "starter_reward": give_avatar,
        "category": "avatars",
        "pay_url": PAY_URL_REFLECTION,
    },
    "puteshestvie": {
        "name": "🌌 Путешествие",
        "price": 1999,
        "description": "Глубокое исследование: карточки историй и полный доступ к GPT-5.",
        "starter_reward": give_next_card,
        "category": "cards",
        "pay_url": PAY_URL_TRAVEL,
    },
}

def activate_tariff(chat_id: int, tariff_key: str):
    if tariff_key not in TARIFFS:
        return None, "❌ Неизвестный тариф"

    tariff = TARIFFS[tariff_key]
    reward_func = tariff["starter_reward"]
    reward = reward_func(chat_id)

    start_date = datetime.date.today()
    end_date = start_date + datetime.timedelta(days=30)

    user_tariffs[chat_id] = {
        "tariff": tariff_key,
        "start": start_date,
        "end": end_date,
    }

    return reward, f"✨ Ты подключил тариф <b>{tariff['name']}</b>!\n\n" \
                   f"{tariff['description']}\n" \
                   f"Подписка активна до: {end_date.strftime('%d.%m.%Y')}"

def check_expiring_tariffs(bot):
    today = datetime.date.today()
    for chat_id, info in list(user_tariffs.items()):
        if info["end"] - today == datetime.timedelta(days=3):
            from bot_utils import offer_renew
            offer_renew(bot, chat_id, info["tariff"])
