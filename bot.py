from telebot import types

# --- Конфиг: значения централизованы в settings.py ---
from settings import bot, client, FREE_LIMIT, PAY_BUTTON_URL

# --- Хранилища состояния пользователей ---
user_counters = {}
user_moods = {}
# Хранилище истории сообщений пользователей
user_histories = {}  # {chat_id: [ {role: "user"/"assistant", content: "..."}, ... ]}

# --- Клавиатуры ---
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("Чек-ин настроения", "Быстрая помощь")
    kb.add("Статистика", "Оплатить подписку")
    return kb

def pay_inline():
    ikb = types.InlineKeyboardMarkup()
    ikb.add(types.InlineKeyboardButton("Оплатить подписку — 299 ₽", url=PAY_BUTTON_URL))
    return ikb

# --- Проверка лимита ---
def check_limit(chat_id) -> bool:
    used = user_counters.get(chat_id, 0)
    if used >= FREE_LIMIT:
        bot.send_message(
            chat_id,
            "🚫 <b>Лимит бесплатных диалогов исчерпан.</b>\n"
            "Оформите подписку за <b>299 ₽/мес.</b> 👇",
            reply_markup=pay_inline(),
        )
        return False
    return True

# --- Helpers ---
def increment_counter(chat_id) -> None:
    """Increase the message counter for a user.

    Creates the counter if it's the first interaction without requiring /start.
    """
    user_counters[chat_id] = user_counters.get(chat_id, 0) + 1

# --- GPT-5 Mini ответ с историей ---
def gpt_answer(chat_id: int, user_text: str) -> str:
    try:
        # Добавляем сообщение пользователя в историю
        history = user_histories.get(chat_id, [])
        history.append({"role": "user", "content": user_text})

        # Ограничиваем историю 5 последними сообщениями
        history = history[-5:]
        user_histories[chat_id] = history

        # Формируем запрос к GPT с системным промптом
        messages = [
            {"role": "system", "content": (
                "Ты — тёплый и внимательный собеседник, как карманный психолог. "
                "Общайся мягко, поэтапно, через вопросы. "
                "Сначала помоги человеку обозначить чувства, потом уточняй детали. "
                "Используй метафоры и образы, чтобы отразить состояние. "
                "Отвечай с эмпатией, поддержкой и теплом. "
                "В конце всегда предлагай маленький реальный шаг, который можно сделать прямо сейчас."
            )}
        ] + history

        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=messages
        )

        reply = response.choices[0].message.content.strip()

        # Добавляем ответ ИИ в историю
        history.append({"role": "assistant", "content": reply})
        user_histories[chat_id] = history[-5:]

        return reply
    except Exception as e:
        return f"⚠️ Ошибка при обращении к GPT: {e}"

# --- Хэндлеры ---
@bot.message_handler(commands=["start"])
def start(m):
    user_counters[m.chat.id] = 0
    user_moods[m.chat.id] = []
    bot.send_message(
        m.chat.id,
        "Привет 👋 Я твой <b>Внутренний GPS</b>.\n\n"
        "• Бесплатно доступны <b>10 диалогов</b>\n"
        "• Подписка: <b>299 ₽/мес.</b>\n\n"
        "Выбирай действие:",
        reply_markup=main_menu(),
    )

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

@bot.message_handler(func=lambda msg: msg.text == "Быстрая помощь")
def quick_help(m):
    if not check_limit(m.chat.id): return
    increment_counter(m.chat.id)
    bot.send_message(
        m.chat.id,
        "🧭 <b>Быстрая помощь</b>\n"
        "• Дыхание 4-7-8\n"
        "• Техника «5 вещей вокруг»\n"
        "• Мышечное расслабление\n",
        reply_markup=main_menu()
    )

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

@bot.message_handler(func=lambda msg: msg.text == "Оплатить подписку")
def pay_button(m):
    bot.send_message(
        m.chat.id,
        "Оплата подписки через ЮKassa. Нажми кнопку ниже 👇",
        reply_markup=pay_inline()
    )

@bot.message_handler(func=lambda msg: msg.text == "⬅️ Назад")
def back_to_menu(m):
    bot.send_message(m.chat.id, "Главное меню:", reply_markup=main_menu())

# --- fallback — если текст не совпал с меню, отправляем в GPT ---
@bot.message_handler(func=lambda msg: True)
def fallback(m):
    if not check_limit(m.chat.id): return
    increment_counter(m.chat.id)
    answer = gpt_answer(m.chat.id, m.text)  # GPT-5 Mini отвечает
    bot.send_message(m.chat.id, answer, reply_markup=main_menu())

# --- Запуск ---
if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True)



