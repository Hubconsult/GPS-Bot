# tariffs.py
"""Tariff definitions and subscription management.

This module describes available tariffs, keeps track of active user
subscriptions and provides helper functions for activating tariffs and
checking for expiring ones.
"""

import datetime

from yookassa import Configuration, Payment

from rewards import give_smile, give_avatar, give_next_card
from settings import (
    PAY_URL_HARMONY,
    PAY_URL_REFLECTION,
    PAY_URL_TRAVEL,
    YOOKASSA_API_KEY,
    YOOKASSA_SHOP_ID,
)


# --- Storage for active subscriptions ---
user_tariffs = {}  # {chat_id: {"tariff": str, "start": date, "end": date}}


# --- Tariff definitions ---
TARIFFS = {
    "sozvuchie": {
        "name": "🌱 Созвучие",
        "price": 299,
        "description": "Первое прикосновение к себе: смайлы и GPT-5 Mini.",
        "starter_reward": give_smile,
        "category": "smiles",
        "pay_url": PAY_URL_HARMONY,
        "media_limits": {"photos": 1, "docs": 1, "analysis": 1},
    },
    "otrazhenie": {
        "name": "🌿 Отражение",
        "price": 999,
        "description": "Видеть себя яснее: аватарки и GPT-5 обычный.",
        "starter_reward": give_avatar,
        "category": "avatars",
        "pay_url": PAY_URL_REFLECTION,
        "media_limits": {"photos": 30, "docs": 10, "analysis": 20},
    },
    "puteshestvie": {
        "name": "🌌 Путешествие",
        "price": 1999,
        "description": "Глубокое исследование: карточки историй и полный доступ к GPT-5.",
        "starter_reward": give_next_card,
        "category": "cards",
        "pay_url": PAY_URL_TRAVEL,
        "media_limits": {"photos": 70, "docs": 20, "analysis": 30},
    },
}


# Настраиваем YooKassa SDK
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_API_KEY


# --- Mapping tariffs to dialogue modes ---
TARIFF_MODES = {
    "sozvuchie": "short_friend",  # 299 ₽ — Короткий друг
    "otrazhenie": "philosopher",  # 999 ₽ — Философ
    "puteshestvie": "academic",   # 1999 ₽ — Академический
}


def start_payment(
    chat_id: int,
    tariff_key: str,
    return_url: str = "https://t.me/VnutrenniyGPS_bot",
) -> str:
    from payments_polling import add_payment

    tariff = TARIFFS[tariff_key]
    payment = Payment.create(
        {
            "amount": {
                "value": f"{tariff['price']:.2f}",
                "currency": "RUB",
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url,
            },
            "capture": True,
            "description": f"Оплата тарифа {tariff['name']}",
            "metadata": {"chat_id": chat_id, "tariff": tariff_key},
        }
    )
    add_payment(chat_id, tariff_key, payment.id)
    return payment.confirmation.confirmation_url


def activate_tariff(chat_id: int, tariff_key: str):
    """Activate a tariff for the given user and grant starter reward."""
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

    message = (
        f"✨ Ты подключил тариф <b>{tariff['name']}</b>!\n\n"
        f"{tariff['description']}\n"
        f"Подписка активна до: {end_date.strftime('%d.%m.%Y')}"
    )
    return reward, message


def check_expiring_tariffs(bot):
    """Notify users whose tariff expires in three days."""
    today = datetime.date.today()
    for chat_id, info in list(user_tariffs.items()):
        if info["end"] - today == datetime.timedelta(days=3):
            from bot_utils import offer_renew
            offer_renew(bot, chat_id, info["tariff"])

