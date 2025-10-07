# bot_utils.py
from tariffs import TARIFFS
from telebot import types

from settings import bot


def offer_renew(bot, chat_id, tariff_key=None):
    text = (
        "⏳ <b>Срок подписки подходит к концу</b>.\n\n"
        "Продолжай общение с SynteraGPT — впереди новые инструменты и открытия."
    )
    kb = types.InlineKeyboardMarkup(row_width=1)
    tariff_name = tariff_key if tariff_key in TARIFFS else "basic"
    tariff = TARIFFS[tariff_name]
    kb.add(
        types.InlineKeyboardButton(
            f"Продлить {tariff['name']} • {tariff['price']} ₽",
            url=tariff["pay_url"],
        )
    )
    bot.send_message(chat_id, text, reply_markup=kb)


def show_typing(chat_id: int) -> None:
    """Показывает пользователю статус «печатает…» в чате Telegram."""
    try:
        bot.send_chat_action(chat_id, "typing")
    except Exception:
        pass
