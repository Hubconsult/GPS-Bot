import re
import threading
import time
import datetime
from pathlib import Path
from typing import Set

from storage import init_db, get_used_free, increment_used
from telebot import types

# Tariff configuration and state tracking
from tariffs import (
    TARIFFS,
    TARIFF_MODES,
    user_tariffs,
    activate_tariff,
    check_expiring_tariffs,
)
from hints import get_hint

# Ensure media handlers are registered
import media

# --- Конфиг: значения централизованы в settings.py ---
from settings import (
    bot,
    client,
    FREE_LIMIT,
    HISTORY_LIMIT,
    is_owner,
    PAY_URL_HARMONY,
    PAY_URL_REFLECTION,
    PAY_URL_TRAVEL,
    SYSTEM_PROMPT,
)

# Initialize the SQLite storage before handling any requests
init_db()

# --- Константы подписки ---
CHANNEL_USERNAME = "@GPT5_Navigator"
CHANNEL_URL = "https://t.me/GPT5_Navigator"
BOT_DEEP_LINK = "https://t.me/VnutrenniyGPS_bot"
PHOTO_FILE = Path(__file__).resolve().parent / "5371038341350424631-1280x720.png"

# --- Хранилища состояния пользователей ---
user_moods = {}
# Хранилище истории сообщений пользователей
user_histories = {}  # {chat_id: [ {role: "user"/"assistant", content: "..."}, ... ]}
user_messages = {}  # {chat_id: [message_id, ...]}

# бесплатный пробник по режимам
user_test_modes = {}  # {chat_id: {"short_friend": 0, "philosopher": 0, "academic": 0}}
# активный тестовый режим
active_test_modes = {}  # {chat_id: mode_key}

# --- Подтверждение подписки ---
verified_users: Set[int] = set()
pending_verification: Set[int] = set()


def has_channel_subscription(user_id: int) -> bool:
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
    except Exception:
        return False
    return status in {"member", "administrator", "creator"}


def subscription_check_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Перейти к боту", callback_data="check_and_open"))
    return kb


def send_subscription_prompt(chat_id: int, user_id: int) -> None:
    caption = (
        "<b>GPT-5 Навигатор</b>\n\n"
        "Добро пожаловать. Это твой внутренний GPS.\n\n"
        "Возможности:\n"
        "— Psychological Astrologer: поиск смыслов в карте жизни\n"
        "— Spiritual Psychologist: понимание глубинных процессов души\n"
        "— Psychological Numerologist: числа как ключи к судьбе\n"
        "— Поддержка 24/7, философские и дружеские разговоры\n"
        "— Работа с фото и документами\n\n"
        "Чтобы перейти к боту, требуется подписка на канал."
    )

    keyboard = subscription_check_keyboard()

    try:
        with PHOTO_FILE.open("rb") as photo:
            bot.send_photo(chat_id, photo, caption=caption, reply_markup=keyboard)
    except FileNotFoundError:
        bot.send_message(chat_id, caption, reply_markup=keyboard)

    pending_verification.add(user_id)


def send_subscription_reminder(chat_id: int, user_id: int, *, force: bool = False) -> None:
    if not force and user_id in pending_verification:
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Подписаться на канал", url=CHANNEL_URL))
    kb.add(types.InlineKeyboardButton("Проверить подписку", callback_data="check_and_open"))

    bot.send_message(
        chat_id,
        (
            "Для использования бота нужно подписаться на канал @GPT5_Navigator.\n"
            "После подписки нажмите «Проверить подписку»."
        ),
        reply_markup=kb,
    )

    pending_verification.add(user_id)


def send_subscription_confirmed(chat_id: int) -> None:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Открыть бота", url=BOT_DEEP_LINK))
    bot.send_message(
        chat_id,
        "Подписка подтверждена. Теперь вы можете перейти к боту.",
        reply_markup=kb,
    )


def ensure_verified(
    chat_id: int,
    user_id: int,
    *,
    remind: bool = True,
    force_check: bool = False,
) -> bool:
    if not force_check and user_id in verified_users:
        return True

    if has_channel_subscription(user_id):
        verified_users.add(user_id)
        pending_verification.discard(user_id)
        return True

    verified_users.discard(user_id)

    if remind:
        send_subscription_reminder(chat_id, user_id)

    return False


def send_and_store(chat_id, text, **kwargs):
    msg = bot.send_message(chat_id, text, **kwargs)
    user_messages.setdefault(chat_id, []).append(msg.message_id)
    return msg

# --- Общие сообщения ---


def send_welcome_menu(chat_id: int) -> None:
    user_moods[chat_id] = []
    text = (
        "<b>Внутренний GPS</b>\n"
        "● online\n\n"
        "Привет 👋 Я твой Внутренний GPS!"
    )
    send_and_store(chat_id, text, reply_markup=main_menu())

# --- Клавиатуры ---

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=4)
    kb.add("Чек-ин", "Стата", "Оплата", "Медиа")
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
    if is_owner(chat_id):
        return True

    if not ensure_verified(chat_id, chat_id, force_check=True):
        return False

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

# --- Получение режима из активного тарифа ---

def get_user_mode(chat_id: int) -> str:
    info = user_tariffs.get(chat_id)
    if not info:
        return "short_friend"
    if info["end"] < datetime.date.today():
        user_tariffs.pop(chat_id, None)
        return "short_friend"
    return TARIFF_MODES.get(info["tariff"], "short_friend")

# --- Обрезаем ответ GPT до 2 предложений ---

def force_short_reply(text: str) -> str:
    sentences = re.split(r'(?<=[.?!])\s+', text)
    return " ".join(sentences[:2]).strip()


# --- Режимы общения ---

MODES = {
    "short_friend": {
        "name": "Короткий друг",
        "system_prompt": (
            "Ты — короткий и дружелюбный собеседник. "
            "Отвечай простыми словами, быстро и поддерживающе, в формате коротких сообщений (3–5 строк). "
            "Не используй длинных объяснений, списков и заголовков. "
            "В каждом ответе должна быть поддержка и один лёгкий вопрос, чтобы продолжить диалог. "
            "Общение должно напоминать переписку с близким другом."
        ),
    },
    "philosopher": {
        "name": "Философ",
        "system_prompt": (
            "Ты — философ. "
            "Веди диалог в стиле размышлений: используй метафоры, истории, примеры. "
            "Первые 3–5 сообщений должны быть рассуждениями и вопросами к пользователю. "
            "Не давай совет сразу — он появляется только после нескольких сообщений, когда яснее понятна суть проблемы. "
            "Не используй заголовков или слов вроде «Совет:». "
            "Отвечай содержательно и образно, чтобы вызывать желание задуматься."
        ),
    },
    "academic": {
        "name": "Академический",
        "system_prompt": (
            "Ты — академический собеседник. "
            "Общайся в универсальном и деловом стиле, опираясь на широкий круг знаний: "
            "научные факты, культурные традиции, символику, числа, а также житейский опыт. "
            "Первые 3–5 сообщений должны включать анализ, пояснения и уточняющие вопросы к пользователю. "
            "Совет давай только после того, как собрал достаточно деталей. "
            "Совет должен быть развёрнутым и аргументированным, но без заголовков. "
            "Всё должно выглядеть как живой, профессиональный диалог."
        ),
    },
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
    if ensure_verified(m.chat.id, m.from_user.id, remind=False, force_check=True):
        send_welcome_menu(m.chat.id)
    else:
        send_subscription_prompt(m.chat.id, m.from_user.id)


@bot.callback_query_handler(func=lambda call: call.data == "check_and_open")
def check_and_open(call):
    was_verified = call.from_user.id in verified_users

    if ensure_verified(call.message.chat.id, call.from_user.id, remind=False, force_check=True):
        if was_verified:
            bot.answer_callback_query(call.id, "✅ Подписка уже подтверждена")
        else:
            bot.answer_callback_query(call.id, "✅ Подписка подтверждена")
            send_subscription_confirmed(call.message.chat.id)

        send_welcome_menu(call.message.chat.id)
    else:
        bot.answer_callback_query(call.id, "❌ Подписка не найдена")
        send_subscription_reminder(call.message.chat.id, call.from_user.id, force=True)

@bot.message_handler(func=lambda msg: msg.text == "Чек-ин")
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

@bot.message_handler(func=lambda msg: msg.text == "Стата")
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

@bot.message_handler(func=lambda msg: msg.text == "Оплата")
def pay_button(m):
    if not ensure_verified(m.chat.id, m.from_user.id, force_check=True):
        return

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
    if not ensure_verified(m.chat.id, m.from_user.id, force_check=True):
        return

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
    if not ensure_verified(m.chat.id, m.from_user.id, force_check=True):
        return

    send_and_store(m.chat.id, "Главное меню:", reply_markup=main_menu())


@bot.callback_query_handler(func=lambda call: call.data == "back")
def callback_back(call):
    bot.answer_callback_query(call.id)

    if not ensure_verified(call.message.chat.id, call.from_user.id, force_check=True):
        return

    send_and_store(
        call.message.chat.id,
        "Главное меню:",
        reply_markup=main_menu()
    )

# --- Команда для показа тарифов ---
@bot.message_handler(commands=["tariffs"])
def show_tariffs(m):
    if not ensure_verified(m.chat.id, m.from_user.id, force_check=True):
        return

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
    if not ensure_verified(m.chat.id, m.from_user.id, force_check=True):
        return

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
    if not ensure_verified(m.chat.id, m.from_user.id, force_check=True):
        return

    parts = m.text.split()
    if len(parts) < 3:
        send_and_store(
            m.chat.id, "❌ Укажи тариф и шаг подсказки: /hint sozvuchie 0"
        )
        return

    tariff_key, step = parts[1], int(parts[2])
    hint_text = get_hint(TARIFFS[tariff_key]["category"], step)
    send_and_store(m.chat.id, f"🔮 Подсказка: {hint_text}")

@bot.message_handler(
    func=lambda msg: any(
        word in msg.text.lower()
        for word in [
            "кто ты",
            "что ты",
            "какая версия",
            "твоя версия",
            "версия гпт",
            "какая модель",
            "твоя модель",
            "модель гпт",
            "структура",
            "архитектура",
            "gpt",
        ]
    )
)
def who_are_you(m):
    if not ensure_verified(m.chat.id, m.from_user.id, force_check=True):
        return

    text = (
        "Я работаю на базе GPT-5, новейшей модели. "
        "GPT-5 обеспечивает более глубокую проработку диалога, высокую точность "
        "и адаптивность, опирается на академические знания и современные исследования. "
        "Модель поддерживает разные стили общения: Короткий друг, Философ и Академический. "
        "Она разработана для того, чтобы вести живой разговор, давать содержательные ответы "
        "и предлагать практические рекомендации на основе психологии. "
        "Использование GPT-5 позволяет создавать осмысленные и развернутые ответы, "
        "которые помогают в самоанализе и принятии решений."
    )
    bot.send_message(m.chat.id, text, reply_markup=main_menu())

# --- Фоновая проверка окончаний подписок и очистка истории ---
def background_checker():
    counter = 0
    while True:
        check_expiring_tariffs(bot)

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

# --- Тестовые режимы ---
@bot.message_handler(commands=["testmodes"])
def test_modes_menu(m):
    if not ensure_verified(m.chat.id, m.from_user.id, force_check=True):
        return

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🎭 Короткий друг (2 сообщения)", callback_data="test_short_friend"),
        types.InlineKeyboardButton("📚 Философ (2 сообщения)", callback_data="test_philosopher"),
        types.InlineKeyboardButton("🧭 Академический (2 сообщения)", callback_data="test_academic"),
    )
    bot.send_message(
        m.chat.id,
        "🔍 Выбери режим, который хочешь попробовать:\nКаждый доступен по 2 бесплатных сообщения.",
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("test_"))
def run_test_mode(call):
    if not ensure_verified(call.message.chat.id, call.from_user.id, force_check=True):
        bot.answer_callback_query(call.id)
        return

    mode_key = call.data.replace("test_", "")
    if call.message.chat.id not in user_test_modes:
        user_test_modes[call.message.chat.id] = {"short_friend": 0, "philosopher": 0, "academic": 0}

    if user_test_modes[call.message.chat.id][mode_key] >= 2:
        bot.answer_callback_query(call.id, "❌ Лимит 2 сообщений в этом режиме исчерпан.")
        return

    bot.answer_callback_query(call.id, f"✅ Пробный режим {MODES[mode_key]['name']} активирован!")
    bot.send_message(call.message.chat.id, f"Спроси меня что-то в режиме <b>{MODES[mode_key]['name']}</b> 👇")

    # фиксируем, что активный тестовый режим запущен
    user_histories[call.message.chat.id] = [{"role": "system", "content": MODES[mode_key]["system_prompt"]}]
    user_test_modes[call.message.chat.id][mode_key] += 1
    active_test_modes[call.message.chat.id] = mode_key

# --- fallback — если текст не совпал с меню, отправляем в GPT ---
@bot.message_handler(func=lambda msg: True)
def fallback(m):
    if not check_limit(m.chat.id): return
    increment_counter(m.chat.id)
    # обработка активного тестового режима
    if m.chat.id in active_test_modes:
        mode_key = active_test_modes[m.chat.id]
        if user_test_modes[m.chat.id][mode_key] < 2:
            answer = gpt_answer(m.chat.id, m.text, mode_key)
            user_test_modes[m.chat.id][mode_key] += 1
            if user_test_modes[m.chat.id][mode_key] >= 2:
                active_test_modes.pop(m.chat.id, None)
            send_and_store(m.chat.id, answer, reply_markup=main_menu())
            return
        else:
            active_test_modes.pop(m.chat.id, None)

    mode = get_user_mode(m.chat.id)
    answer = gpt_answer(m.chat.id, m.text, mode)
    send_and_store(m.chat.id, answer, reply_markup=main_menu())

# --- Запуск ---
if __name__ == "__main__":
    threading.Thread(target=background_checker, daemon=True).start()
    bot.infinity_polling(skip_pending=True)



