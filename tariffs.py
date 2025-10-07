# tariffs.py
"""Tariff definitions and subscription management."""

import datetime
import random
import sqlite3
from typing import Optional

from yookassa import Configuration, Payment

from rewards import ICON_REWARDS, send_reward
from settings import CRM_TARIFF_CODE, PAY_URL_HARMONY, YOOKASSA_API_KEY, YOOKASSA_SHOP_ID, r
from storage import DB_PATH


# --- Storage for active subscriptions ---
user_tariffs = {}  # {chat_id: {"tariff": str, "start": date, "end": date}}

# Explicit re-export list helps static analyzers and prevents merge conflict
# markers from sneaking into the module when resolving future edits.
__all__ = [
    "BASIC_TARIFF_KEY",
    "TARIFFS",
    "TARIFF_MODES",
    "user_tariffs",
    "start_payment",
    "activate_tariff",
    "check_expiring_tariffs",
    "get_crm_access_code",
]


# --- Tariff definitions ---

BASIC_TARIFF_KEY = "basic"
TARIFFS = {
    BASIC_TARIFF_KEY: {
        "name": "Basic",
        "price": 299,
        "description": "SynteraGPT Basic — короткие ответы и базовые функции без выхода в интернет.",
        "starter_reward": lambda chat_id: send_reward(chat_id, random.choice(ICON_REWARDS)),
        "category": "basic",
        "pay_url": PAY_URL_HARMONY,
        "media_limits": {"photos": 1, "docs": 1, "analysis": 1},
        "crm_code": CRM_TARIFF_CODE,
    }
}


# Настраиваем YooKassa SDK
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_API_KEY


# --- Mapping tariffs to dialogue modes ---
TARIFF_MODES = {
    BASIC_TARIFF_KEY: "short_friend",  # 299₽ — короткие поддерживающие ответы
}


def start_payment(
    chat_id: int,
    tariff_key: str,
    return_url: str = "https://t.me/SynteraGPT_bot",
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
    reward_title = reward.get("title") if isinstance(reward, dict) else str(reward)

    start_date = datetime.date.today()
    end_date = start_date + datetime.timedelta(days=30)

    user_tariffs[chat_id] = {
        "tariff": tariff_key,
        "start": start_date,
        "end": end_date,
    }

    # фиксируем в базе
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users(chat_id, used_free, has_tariff) VALUES(?, 0, 1)",
        (chat_id,),
    )
    c.execute("UPDATE users SET has_tariff=1 WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()

    crm_code = tariff.get("crm_code")
    _persist_crm_access(chat_id, crm_code, start_date, end_date)

    message = (
        f"✨ Ты подключил тариф <b>{tariff['name']}</b>!\n\n"
        f"{tariff['description']}\n"
        f"Подписка активна до: {end_date.strftime('%d.%m.%Y')}\n"
        f"Твоя первая награда: {reward_title}"
    )
    return reward, message


def check_expiring_tariffs(bot):
    """Notify users whose tariff expires in three days."""
    today = datetime.date.today()
    for chat_id, info in list(user_tariffs.items()):
        if info["end"] - today == datetime.timedelta(days=3):
            from bot_utils import offer_renew
            offer_renew(bot, chat_id, info["tariff"])


def _persist_crm_access(
    chat_id: int,
    crm_code: Optional[str],
    start_date: datetime.date,
    end_date: datetime.date,
) -> None:
    """Store CRM access code in Redis for the duration of the tariff."""

    if not crm_code or r is None:
        return

    ttl_seconds = int((end_date - start_date).total_seconds())
    if ttl_seconds <= 0:
        ttl_seconds = 30 * 24 * 60 * 60  # fallback to 30 days

    key = f"user:{chat_id}:tariff"
    try:
        r.setex(key, ttl_seconds, crm_code)
    except Exception:
        # Redis is optional; ignore failures silently so activation succeeds.
        pass


def get_crm_access_code(chat_id: int) -> Optional[str]:
    """Return the CRM access code stored in Redis for the user, if available."""

    if r is None:
        return None

    try:
        value = r.get(f"user:{chat_id}:tariff")
    except Exception:
        return None

    if value is None:
        return None

    if isinstance(value, bytes):
        value = value.decode("utf-8")

    return str(value)

