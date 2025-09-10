import re
import threading
import time

from telebot import types

from tariffs import TARIFFS, activate_tariff, check_expiring_tariffs
from hints import get_hint
from bot_utils import offer_renew

# --- Конфиг: значения централизованы в settings.py ---
from settings import (
    bot,
    client,
    FREE_LIMIT,
    HISTORY_LIMIT,
    OWNER_IDS,
    PAY_URL_HARMONY,
    PAY_URL_REFLECTION,
    PAY_URL_TRAVEL,
    SYSTEM_PROMPT,
)

# --- Хранилища состояния пользователей ---
user_counters = {}
user_moods = {}
# Хранилище истории сообщений пользователей
user_histories = {}  # {chat_id: [ {role: "user"/"assistant", content: "..."}, ... ]}

# --- Клавиатуры ---
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    kb.add("Чек-ин настроения", "Статистика", "Оплатить")
    return kb


def pay_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add("🌱 Созвучие — 299 ₽")
    kb.add("🌿 Отражение — 999 ₽")
    kb.add("🌌 Путешествие — 1999 ₽")
    kb.add("⬅️ Назад")
    return kb

# --- Проверка лимита ---
def check_limit(chat_id) -> bool:
    # 🚀 Владельцу бота лимиты не применяются
    if chat_id in OWNER_IDS:
        return True

    used = user_counters.get(chat_id, 0)
    if used >= FREE_LIMIT:
        bot.send_message(
            chat_id,
            "🚫 <b>Лимит бесплатных диалогов исчерпан.</b>\n"
            "Выберите тариф 👇",
            reply_markup=pay_menu(),
        )
        return False
    return True

# --- Helpers ---
def increment_counter(chat_id) -> None:
    """Increase the message counter for a user.

    Creates the counter if it's the first interaction without requiring /start.
    """
    user_counters[chat_id] = user_counters.get(chat_id, 0) + 1

# --- Обрезаем ответ GPT до 2 предложений ---
def force_short_reply(text: str) -> str:
    sentences = re.split(r'(?<=[.?!])\s+', text)
    return " ".join(sentences[:2]).strip()


# --- GPT-5 Mini ответ с историей ---
def gpt_answer(chat_id: int, user_text: str) -> str:
    try:
        history = user_histories.get(chat_id, [])
        history.append({"role": "user", "content": user_text})
        history = history[-HISTORY_LIMIT:]
        user_histories[chat_id] = history

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "assistant",
                "content": "Слышу, что тебе тяжело. Скажи, это больше похоже на усталость или на тревогу?",
            },
        ] + history

        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=messages,
        )

        reply = response.choices[0].message.content.strip()
        reply = force_short_reply(reply)  # обрезаем всё длиннее 2 предложений

        history.append({"role": "assistant", "content": reply})
        user_histories[chat_id] = history[-HISTORY_LIMIT:]

        return reply
    except Exception as e:
        return f"⚠️ Ошибка при обращении к GPT: {e}"

# --- Хэндлеры ---
@bot.message_handler(commands=["start"])
def start(m):
    user_counters[m.chat.id] = 0
    user_moods[m.chat.id] = []
    text = (
        "<b>Внутренний GPS</b>\n"
        "● online\n\n"
        "Привет 👋 Я твой Внутренний GPS!"
    )
    bot.send_message(m.chat.id, text, reply_markup=main_menu())

@bot.message_handler(func=lambda msg: msg.text == "Чек-ин настроения")
def mood_start(m):
    if not check_limit(m.chat.id): return
    increment_counter(m.chat.id)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=4, one_time_keyboard=True)
    kb.add("😊", "😟", "😴", "😡")
    kb.add("⬅️ Назад")
    bot.send_message(m.chat.id, "Выбери смайлик, который ближе к твоему состоянию:", reply_markup=kb)

@bot.message_handler(func=lambda msg: msg.text in ["😊", "😟", "😴", "😡"])
def mood_save(m):
    if not check_limit(m.chat.id): return
    increment_counter(m.chat.id)
    user_moods.setdefault(m.chat.id, []).append(m.text)
    bot.send_message(m.chat.id, f"Принял {m.text}. Спасибо за отметку!", reply_markup=main_menu())

@bot.message_handler(func=lambda msg: msg.text == "Статистика")
def stats(m):
    if not check_limit(m.chat.id): return
    increment_counter(m.chat.id)
    moods = user_moods.get(m.chat.id, [])
    counts = {e: moods.count(e) for e in ["😊", "😟", "😴", "😡"]}
    bot.send_message(
        m.chat.id,
        f"📊 <b>Твоя неделя</b>\n"
        f"😊 Радость: {counts['😊']}\n"
        f"😟 Тревога: {counts['😟']}\n"
        f"😴 Усталость: {counts['😴']}\n"
        f"😡 Злость: {counts['😡']}",
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda msg: msg.text == "Оплатить")
def pay_button(m):
    bot.send_message(
        m.chat.id,
        "Выбери тариф 👇",
        reply_markup=pay_menu()
    )


@bot.message_handler(
    func=lambda msg: msg.text in [
        "🌱 Созвучие — 299 ₽",
        "🌿 Отражение — 999 ₽",
        "🌌 Путешествие — 1999 ₽",
    ]
)
def tariffs(m):
    if "Созвучие" in m.text:
        url = PAY_URL_HARMONY
    elif "Отражение" in m.text:
        url = PAY_URL_REFLECTION
    else:
        url = PAY_URL_TRAVEL

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Перейти к оплате 💳", url=url))
    kb.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back"))

    bot.send_message(m.chat.id, f"Ты выбрал: {m.text}", reply_markup=kb)

@bot.message_handler(func=lambda msg: msg.text == "⬅️ Назад")
def back_to_menu(m):
    bot.send_message(m.chat.id, "Главное меню:", reply_markup=main_menu())


@bot.callback_query_handler(func=lambda call: call.data == "back")
def callback_back(call):
    bot.send_message(
        call.message.chat.id,
        "Главное меню:",
        reply_markup=main_menu()
    )

# --- Команда для показа тарифов ---
@bot.message_handler(commands=["tariffs"])
def show_tariffs(m):
    text = "📜 <b>Выбери свой путь</b>\n\n"
    for key, t in TARIFFS.items():
        text += f"{t['name']} — {t['price']} ₽/мес.\n{t['description']}\n\n"

    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, t in TARIFFS.items():
        kb.add(
            types.InlineKeyboardButton(
                f"{t['name']} • {t['price']} ₽", url=t["pay_url"]
            )
        )

    bot.send_message(m.chat.id, text, reply_markup=kb)

# --- Активация тарифа ---
@bot.message_handler(commands=["activate"])
def activate(m):
    parts = m.text.split()
    if len(parts) < 2:
        bot.send_message(
            m.chat.id,
            "❌ Укажи тариф: sozvuchie, otrazhenie или puteshestvie",
        )
        return

    tariff_key = parts[1]
    reward, msg = activate_tariff(m.chat.id, tariff_key)
    if reward:
        bot.send_message(m.chat.id, f"{msg}\n\nТвоя первая награда: {reward}")
    else:
        bot.send_message(m.chat.id, msg)

# --- Подсказка ---
@bot.message_handler(commands=["hint"])
def hint(m):
    parts = m.text.split()
    if len(parts) < 3:
        bot.send_message(
            m.chat.id, "❌ Укажи тариф и шаг подсказки: /hint sozvuchie 0"
        )
        return

    tariff_key, step = parts[1], int(parts[2])
    hint_text = get_hint(TARIFFS[tariff_key]["category"], step)
    bot.send_message(m.chat.id, f"🔮 Подсказка: {hint_text}")

# --- Фоновая проверка окончаний подписок ---
def background_checker():
    while True:
        check_expiring_tariffs(bot)
        time.sleep(86400)  # раз в сутки

# --- fallback — если текст не совпал с меню, отправляем в GPT ---
@bot.message_handler(func=lambda msg: True)
def fallback(m):
    if not check_limit(m.chat.id): return
    increment_counter(m.chat.id)
    answer = gpt_answer(m.chat.id, m.text)  # GPT-5 Mini отвечает
    bot.send_message(m.chat.id, answer, reply_markup=main_menu())

# --- Запуск ---
if __name__ == "__main__":
    threading.Thread(target=background_checker, daemon=True).start()
    bot.infinity_polling(skip_pending=True)



