import re
import threading
import time

from storage import init_db, get_used_free, increment_used
from telebot import types

from tariffs import (
    TARIFFS,
    TARIFF_MODES,
    user_tariffs,
    activate_tariff,
    check_expiring_tariffs,
)
from hints import get_hint

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

# Initialize the SQLite storage before handling any requests
init_db()

# --- Хранилища состояния пользователей ---
user_moods = {}
# Хранилище истории сообщений пользователей
user_histories = {}  # {chat_id: [ {role: "user"/"assistant", content: "..."}, ... ]}
user_messages = {}  # {chat_id: [message_id, ...]}

# бесплатный пробник по режимам
user_test_modes = {}  # {chat_id: {"short_friend": 0, "philosopher": 0, "coach": 0}}


# --- Режимы, доступные пользователю ---
def get_user_modes(chat_id):
    info = user_tariffs.get(chat_id)
    if not info:
        return ["short_friend"]
    return TARIFF_MODES.get(info["tariff"], ["short_friend"])


def send_and_store(chat_id, text, **kwargs):
    msg = bot.send_message(chat_id, text, **kwargs)
    user_messages.setdefault(chat_id, []).append(msg.message_id)
    return msg

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

def pay_inline():
    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, t in TARIFFS.items():
        kb.add(
            types.InlineKeyboardButton(
                f"{t['name']} • {t['price']} ₽", url=t["pay_url"]
            )
        )
    return kb

# --- Проверка лимита ---
def check_limit(chat_id) -> bool:
    if chat_id in OWNER_IDS:
        return True
    used = get_used_free(chat_id)
    if used >= FREE_LIMIT:
        bot.send_message(
            chat_id,
            "🚫 <b>Лимит бесплатных диалогов исчерпан.</b>\nВыберите тариф 👇",
            reply_markup=pay_inline(),
        )
        return False
    return True

# --- Helpers ---
def increment_counter(chat_id) -> None:
    increment_used(chat_id)

# --- Обрезаем ответ GPT до 2 предложений ---
def force_short_reply(text: str) -> str:
    sentences = re.split(r'(?<=[.?!])\s+', text)
    return " ".join(sentences[:2]).strip()


# --- Режимы общения ---
MODES = {
    "short_friend": {
        "name": "Короткий друг",
        "system_prompt": "Ты — добрый и лёгкий собеседник. Отвечай коротко, тепло, по-дружески. Не задавай больше одного вопроса за раз.",
    },
    "philosopher": {
        "name": "Философ",
        "system_prompt": "Ты — мудрый философ. Отвечай развёрнуто, с метафорами, примерами, глубокими размышлениями. Можно задавать уточняющие вопросы, но максимум 2 подряд, затем всегда давать содержательный ответ.",
    },
    "coach": {
        "name": "Коуч",
        "system_prompt": "Ты — коуч и наставник. Помогаешь разложить проблему на шаги. Используй эмпатию, уточняй детали, но не больше 2 вопросов подряд. Каждый ответ содержит полезный совет и один вопрос для движения вперёд.",
    }
}

# --- GPT-5 Mini ответ с историей ---
def gpt_answer(chat_id: int, user_text: str, mode_key: str = "short_friend") -> str:
    try:
        history = user_histories.get(chat_id, [])
        history.append({"role": "user", "content": user_text})
        history = history[-10:]
        user_histories[chat_id] = history

        system_prompt = MODES[mode_key]["system_prompt"]

        messages = [{"role": "system", "content": system_prompt}] + history

        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=messages,
        )

        reply = response.choices[0].message.content.strip()
        history.append({"role": "assistant", "content": reply})
        user_histories[chat_id] = history[-10:]

        return reply
    except Exception as e:
        return f"⚠️ Ошибка при обращении к GPT: {e}"

# --- Хэндлеры ---
@bot.message_handler(commands=["start"])
def start(m):
    user_moods[m.chat.id] = []
    text = (
        "<b>Внутренний GPS</b>\n"
        "● online\n\n"
        "Привет 👋 Я твой Внутренний GPS!"
    )
    send_and_store(m.chat.id, text, reply_markup=main_menu())

@bot.message_handler(func=lambda msg: msg.text == "Чек-ин настроения")
def mood_start(m):
    if not check_limit(m.chat.id): return
    increment_counter(m.chat.id)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=4, one_time_keyboard=True)
    kb.add("😊", "😟", "😴", "😡")
    kb.add("⬅️ Назад")
    send_and_store(m.chat.id, "Выбери смайлик, который ближе к твоему состоянию:", reply_markup=kb)

@bot.message_handler(func=lambda msg: msg.text in ["😊", "😟", "😴", "😡"])
def mood_save(m):
    if not check_limit(m.chat.id): return
    increment_counter(m.chat.id)
    user_moods.setdefault(m.chat.id, []).append(m.text)
    send_and_store(m.chat.id, f"Принял {m.text}. Спасибо за отметку!", reply_markup=main_menu())

@bot.message_handler(func=lambda msg: msg.text == "Статистика")
def stats(m):
    if not check_limit(m.chat.id): return
    increment_counter(m.chat.id)
    moods = user_moods.get(m.chat.id, [])
    counts = {e: moods.count(e) for e in ["😊", "😟", "😴", "😡"]}
    send_and_store(
        m.chat.id,
        f"📊 <b>Твоя неделя</b>\n"
        f"😊 Радость: {counts['😊']}\n"
        f"😟 Тревога: {counts['😟']}\n"
        f"😴 Усталость: {counts['😴']}\n"
        f"😡 Злость: {counts['😡']}",
        reply_markup=main_menu(),
    )

@bot.message_handler(func=lambda msg: msg.text == "Оплатить")
def pay_button(m):
    send_and_store(
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

    send_and_store(m.chat.id, f"Ты выбрал: {m.text}", reply_markup=kb)

@bot.message_handler(func=lambda msg: msg.text == "⬅️ Назад")
def back_to_menu(m):
    send_and_store(m.chat.id, "Главное меню:", reply_markup=main_menu())


@bot.callback_query_handler(func=lambda call: call.data == "back")
def callback_back(call):
    send_and_store(
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

    send_and_store(m.chat.id, text, reply_markup=kb)

# --- Активация тарифа ---
@bot.message_handler(commands=["activate"])
def activate(m):
    parts = m.text.split()
    if len(parts) < 2:
        send_and_store(
            m.chat.id,
            "❌ Укажи тариф: sozvuchie, otrazhenie или puteshestvie",
        )
        return

    tariff_key = parts[1]
    reward, msg = activate_tariff(m.chat.id, tariff_key)
    if reward:
        send_and_store(m.chat.id, f"{msg}\n\nТвоя первая награда: {reward}")
    else:
        send_and_store(m.chat.id, msg)

# --- Подсказка ---
@bot.message_handler(commands=["hint"])
def hint(m):
    parts = m.text.split()
    if len(parts) < 3:
        send_and_store(
            m.chat.id, "❌ Укажи тариф и шаг подсказки: /hint sozvuchie 0"
        )
        return

    tariff_key, step = parts[1], int(parts[2])
    hint_text = get_hint(TARIFFS[tariff_key]["category"], step)
    send_and_store(m.chat.id, f"🔮 Подсказка: {hint_text}")

@bot.message_handler(func=lambda msg: "структур" in msg.text.lower() or "кто ты" in msg.text.lower() or "gpt" in msg.text.lower())
def who_are_you(m):
    text = (
        "✨ Я — <b>GPT-5</b>, новейшая модель от OpenAI.\n\n"
        "📌 Мои особенности:\n"
        "• Объединяю быстрые ответы и глубокое рассуждение.\n"
        "• Выдаю более точные результаты, чем предыдущие версии.\n"
        "• Силен в программировании, письме, медицине и анализе сложных тем.\n"
        "• Мультимодальность: умею работать с текстом и изображениями.\n"
        "• Эмпатия и адаптация: подстраиваюсь под стиль общения, помню контекст.\n"
        "• Умею рассуждать шаг за шагом и объяснять причины.\n\n"
        "Так что да — я <b>GPT-5</b> 🚀"
    )
    bot.send_message(m.chat.id, text, reply_markup=main_menu())

# --- Фоновая проверка окончаний подписок и очистка истории ---
def background_checker():
    counter = 0
    while True:
        check_expiring_tariffs(send_and_store)

        if counter % 7 == 0:
            user_histories.clear()
            for chat_id, msgs in user_messages.items():
                for msg_id in msgs:
                    try:
                        bot.delete_message(chat_id, msg_id)
                    except Exception:
                        pass
            user_messages.clear()
            print("🧹 История всех пользователей и сообщения очищены")

        counter += 1
        time.sleep(86400)  # раз в сутки

# --- fallback — если текст не совпал с меню, отправляем в GPT ---
@bot.message_handler(func=lambda msg: True)
def fallback(m):
    if not check_limit(m.chat.id): return
    increment_counter(m.chat.id)
    # бесплатный пробник по 2 сообщения из каждого режима
    if m.chat.id not in user_test_modes:
        user_test_modes[m.chat.id] = {"short_friend": 0, "philosopher": 0, "coach": 0}

    test_counts = user_test_modes[m.chat.id]

    allowed_modes = get_user_modes(m.chat.id)

    if test_counts["short_friend"] < 2:
        user_test_modes[m.chat.id]["short_friend"] += 1
        answer = gpt_answer(m.chat.id, m.text, "short_friend")
    elif "philosopher" in allowed_modes and test_counts["philosopher"] < 2:
        user_test_modes[m.chat.id]["philosopher"] += 1
        answer = gpt_answer(m.chat.id, m.text, "philosopher")
    elif "coach" in allowed_modes and test_counts["coach"] < 2:
        user_test_modes[m.chat.id]["coach"] += 1
        answer = gpt_answer(m.chat.id, m.text, "coach")
    else:
        mode = allowed_modes[0]
        answer = gpt_answer(m.chat.id, m.text, mode)

    send_and_store(m.chat.id, answer, reply_markup=main_menu())

# --- Запуск ---
if __name__ == "__main__":
    threading.Thread(target=background_checker, daemon=True).start()
    bot.infinity_polling(skip_pending=True)



