import threading
import time
import logging
import datetime
from threading import Lock
from contextlib import suppress
from pathlib import Path
from typing import Set

from storage import (
    init_db,
    get_user_usage,
    increment_used,
    clear_history,
    iter_history_chat_ids,
    r,
    TTL,
)
from telebot import types

# Tariff configuration and state tracking
from tariffs import (
    TARIFFS,
    TARIFF_MODES,
    user_tariffs,
    activate_tariff,
    check_expiring_tariffs,
    start_payment,
)
from hints import get_hint
from info import get_info_text, info_keyboard

# Ensure media handlers are registered
import media
from media import multimedia_menu

from bot_utils import show_typing

# --- Конфиг: значения централизованы в settings.py ---
from settings import (
    bot,
    client,
    CHAT_MODEL,
    FREE_LIMIT,
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
START_CAPTION = (
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

# --- Хранилища состояния пользователей ---
user_moods = {}
# Хранилище истории сообщений пользователей (локальный кэш)
user_histories = {}  # {chat_id: [ {role: "user"/"assistant", content: "..."}, ... ]}
user_messages = {}  # {chat_id: [message_id, ...]}

# бесплатный пробник по режимам
user_test_modes = {}  # {chat_id: str}
user_test_mode_usage = {}  # {chat_id: {"short_friend": int, "philosopher": int, "academic": int}}

# кеш выбранного языка (для офлайн-режима, если Redis недоступен)
_language_cache: dict[int, str] = {}

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


def pay_inline(chat_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, tariff in TARIFFS.items():
        url = start_payment(chat_id, key)
        kb.add(
            types.InlineKeyboardButton(
                f"{tariff['name']} • {tariff['price']} ₽", url=url
            )
        )
    return kb


def send_start_window(chat_id) -> None:
    keyboard = subscription_check_keyboard()

    try:
        with PHOTO_FILE.open("rb") as photo:
            bot.send_photo(
                chat_id,
                photo,
                caption=START_CAPTION,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
    except FileNotFoundError:
        bot.send_message(
            chat_id,
            START_CAPTION,
            reply_markup=keyboard,
            parse_mode="HTML",
        )


def send_subscription_prompt(chat_id: int, user_id: int) -> None:
    send_start_window(chat_id)
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


# --- Регистрируем кнопки в меню Telegram (будут видны в канале под строкой чата)
bot.set_my_commands([
    types.BotCommand("info", "Тарифы и возможности GPT-5"),
    types.BotCommand("pay", "Оплата тарифов"),
    types.BotCommand("media", "Мультимедиа"),
    types.BotCommand("profile", "Профиль"),
])


# --- /info
@bot.message_handler(commands=["info"])
def cmd_info(m):
    bot.send_message(
        m.chat.id,
        get_info_text(),
        reply_markup=info_keyboard(),
        parse_mode="HTML",
    )


# --- /pay
@bot.message_handler(commands=["pay"])
def cmd_pay(m):
    if not ensure_verified(m.chat.id, m.from_user.id, force_check=True):
        return

    bot.send_message(
        m.chat.id,
        "Выберите тариф:",
        reply_markup=pay_inline(m.chat.id),
    )


# --- /media
@bot.message_handler(commands=["media"])
def cmd_media(m):
    bot.send_message(
        m.chat.id,
        "Доступные мультимедиа функции:",
        reply_markup=multimedia_menu(),
    )


# --- /profile
@bot.message_handler(commands=["profile"])
def cmd_profile(m):
    bot.send_message(
        m.chat.id,
        f"Ваш ID: {m.from_user.id}\n"
        f"Имя: {m.from_user.first_name}\n"
        "Подписка: FREE (по умолчанию)",
    )


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
    kb.add("Очистить", "Lang 🌐")
    return kb


def pay_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add("Созвучие • иконки — 299 ₽")
    kb.add("Отражение • аватарки — 999 ₽")
    kb.add("Путешествие • истории и фоны — 1999 ₽")
    kb.add("⬅️ Назад")
    return kb

# --- Работа с языком ---


def set_language(chat_id: int, lang: str) -> None:
    try:
        r.set(f"lang:{chat_id}", lang, ex=TTL)
    except Exception:
        pass
    _language_cache[chat_id] = lang


def get_language(chat_id: int) -> str:
    try:
        lang = r.get(f"lang:{chat_id}")
    except Exception:
        lang = None

    if lang:
        if isinstance(lang, bytes):
            lang = lang.decode("utf-8")
        _language_cache[chat_id] = str(lang)
        return str(lang)

    return _language_cache.get(chat_id, "ru")

# --- Проверка лимита ---

def check_limit(chat_id) -> bool:
    if is_owner(chat_id):
        return True

    if not ensure_verified(chat_id, chat_id, force_check=True):
        return False

    used, has_tariff = get_user_usage(chat_id)
    if has_tariff == 0 and used >= FREE_LIMIT:
        bot.send_message(
            chat_id,
            "🚫 <b>Лимит бесплатных диалогов исчерпан.</b>\nВыберите тариф 👇",
            reply_markup=pay_inline(chat_id),
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

# --- Режимы общения ---

MODES = {
    "short_friend": {
        "name": "Короткий друг",
        "system_prompt": (
            "Ты — дружелюбный и поддерживающий собеседник, как близкий друг. "
            "Общайся тепло, мягко и эмпатично. Каждый ответ должен быть связным и "
            "занимать от 5 до 8 строчек, 95% текста — содержательный ответ, 5% — "
            "короткий вопрос в конце. После первого сообщения можно задать только "
            "один уточняющий вопрос. Избегай любых советов с упражнениями, "
            "медитациями, дыхательными практиками или техниками — веди только "
            "живой разговор."
        ),
    },
    "philosopher": {
        "name": "Философ",
        "system_prompt": (
            "Ты — мудрый философ и наставник. Используй метафоры, истории и "
            "рассуждения, чтобы помочь взглянуть глубже. Отвечай от 5 до 8 "
            "строчек, 95% текста — размышления и поддержка, 5% — короткий "
            "вопрос в конце. Допускается один уточняющий вопрос после первого "
            "сообщения. Никогда не предлагай упражнений, медитаций, дыхательных "
            "техник или пошаговых практик — только живой диалог и рассуждения."
        ),
    },
    "academic": {
        "name": "Академический",
        "system_prompt": (
            "Ты — академический собеседник, объясняющий через науку, культуру, "
            "числа и символы. Стиль живой и поддерживающий, без сухих лекций. "
            "Ответы занимают 5–8 строчек (95% — анализ и поддержка, 5% — вопрос "
            "в конце). После первого сообщения допускается один уточняющий "
            "вопрос. Исключи любые советы по медитациям, дыханию, упражнениям "
            "или техникам. Веди диалог как интеллектуальное обсуждение."
        ),
    },
}

TEST_BUTTONS = ["Друг", "Философ", "Академик"]
TEST_BUTTON_CONFIG = {
    "Друг": ("🎭", "short_friend"),
    "Философ": ("📚", "philosopher"),
    "Академик": ("🧭", "academic"),
}

# --- GPT-5 Mini ответ с потоковой выдачей ---

EDIT_INTERVAL = 0.4             # не слишком частые редактирования (сек)
FIRST_CHUNK_TOKENS = 12         # показать быстро несколько токенов
STREAM_STALL_TIMEOUT = 30.0     # увеличили с 12.0, даём стриму до 30 секунд тишины
MAX_RETRIES = 3                 # увеличили число попыток с 2 до 3
BACKOFF_BASE = 1.0              # базовая пауза при retry (сек)

# Статический словарь блокировок по chat_id — предотвращает параллельные стримы в одном чате.
_chat_locks: dict[int, Lock] = {}
_logger = logging.getLogger("gpsbot.stream")
_logger.setLevel(logging.INFO)
Path("/root/GPS-Bot/logs").mkdir(parents=True, exist_ok=True)
# настроим простой file handler (по желанию)
fh = logging.FileHandler("/root/GPS-Bot/logs/stream_gpt.log")
fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
_logger.addHandler(fh)


def _coerce_content_to_text(content) -> str:
    """Приводит разные форматы контента OpenAI к строке."""

    if content is None:
        return ""
    if isinstance(content, str):
        return content

    # Новые SDK могут возвращать объекты с атрибутом text
    text_attr = getattr(content, "text", None)
    if isinstance(text_attr, str):
        return text_attr
    if text_attr is not None:
        return _coerce_content_to_text(text_attr)

    if isinstance(content, list):
        parts = [_coerce_content_to_text(item) for item in content]
        return "".join(parts)

    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content.get("text", "")
        if "content" in content:
            return _coerce_content_to_text(content["content"])
        if "value" in content:
            return _coerce_content_to_text(content["value"])

    return str(content)


def _extract_message_text(message) -> str:
    if message is None:
        return ""

    if isinstance(message, dict):
        return _coerce_content_to_text(message.get("content"))

    content = getattr(message, "content", None)
    text = _coerce_content_to_text(content)
    if text:
        return text

    # fallback: иногда текст может лежать в message.text
    return _coerce_content_to_text(getattr(message, "text", ""))


def _get_chat_lock(chat_id: int) -> Lock:
    """Возвращает (и создаёт при необходимости) Lock для конкретного чата."""
    lock = _chat_locks.get(chat_id)
    if lock is None:
        lock = Lock()
        _chat_locks[chat_id] = lock
    return lock


def _safe_get_delta_content(chunk) -> str | None:
    """
    Универсально извлекает текстовый фрагмент из stream-chunk.
    Поддерживает:
     - chunk.choices[0].delta.content (обычно для incremental stream)
     - chunk.choices[0].message.content (иногда финальный текст приходит в message)
     - dict-like структуры от разных SDK
    Возвращает строку или None.
    """
    try:
        # 1) new style: chunk.choices[0].delta.content
        delta = getattr(getattr(chunk, "choices", [None])[0], "delta", None)
        if delta is not None:
            # объектный интерфейс
            content = _coerce_content_to_text(getattr(delta, "content", None))
            if content:
                return content
            # dict-like delta
            if isinstance(delta, dict):
                c = _coerce_content_to_text(delta.get("content"))
                if c:
                    return c

        # 2) sometimes final message is in choices[0].message.content
        choice0 = None
        try:
            choice0 = chunk.choices[0]
        except Exception:
            pass

        if choice0 is not None:
            # try object-style message
            msg = getattr(choice0, "message", None)
            if msg is not None:
                content = _coerce_content_to_text(getattr(msg, "content", None))
                if content:
                    return content
                if isinstance(msg, dict):
                    c = _coerce_content_to_text(msg.get("content"))
                    if c:
                        return c

        # 3) dict-like root fallback: chunk["choices"][0]["message"]["content"] or delta
        if isinstance(chunk, dict):
            try:
                ch0 = chunk.get("choices", [None])[0]
                if ch0:
                    # prefer delta.content
                    d = ch0.get("delta")
                    if isinstance(d, dict):
                        c = _coerce_content_to_text(d.get("content"))
                        if c:
                            return c
                    # then try message.content
                    m = ch0.get("message")
                    if isinstance(m, dict):
                        c = _coerce_content_to_text(m.get("content"))
                        if c:
                            return c
            except Exception:
                pass

    except Exception:
        return None

    return None


def stream_gpt_answer(chat_id: int, user_text: str, mode_key: str = "short_friend") -> None:
    """
    Отправляет запрос в GPT-5 mini без стриминга и сразу возвращает полный ответ.
    В случае ошибки возвращает сообщение об ошибке, чтобы пользователь не оставался с «…».
    """
    lock = _get_chat_lock(chat_id)
    if not lock.acquire(blocking=False):
        with suppress(Exception):
            bot.send_message(chat_id, "⚠️ Уже формируется ответ в этом чате. Подождите, пожалуйста.")
        return

    try:
        # Добавляем новое сообщение пользователя в историю
        history = user_histories.get(chat_id, [])
        history.append({"role": "user", "content": user_text})
        short_history = history[-6:]
        system_prompt = MODES[mode_key]["system_prompt"]
        messages = [{"role": "system", "content": system_prompt}] + short_history

        # Показываем «печатает..."
        show_typing(chat_id)
        draft = bot.send_message(chat_id, "…", reply_markup=main_menu())
        msg_id = draft.message_id

        # Синхронный (нестриминговый) запрос к GPT
        try:
            resp = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                stream=False,
                max_completion_tokens=800  # длинные ответы умещаются без обрезки
            )
            # Получаем текст ответа
            final_text = _extract_message_text(resp.choices[0].message).strip()
            if not final_text:
                final_text = "⚠️ Ответ пуст."
        except Exception as e:
            import traceback

            print("❌ Ошибка GPT:", e)
            traceback.print_exc()
            _logger.exception("Non-stream call failed")
            final_text = "⚠️ Ошибка при генерации ответа. Попробуйте позже."

        # Отправляем или редактируем сообщение
        try:
            bot.edit_message_text(final_text, chat_id, msg_id, parse_mode="HTML")
        except Exception:
            with suppress(Exception):
                bot.send_message(chat_id, final_text, parse_mode="HTML")

        # Сохраняем ответ в историю
        short_history.append({"role": "assistant", "content": final_text})
        user_histories[chat_id] = short_history[-6:]

    finally:
        with suppress(Exception):
            lock.release()

# --- Хэндлеры ---
@bot.message_handler(commands=["start"])
def start(m):
    send_subscription_prompt(m.chat.id, m.from_user.id)


@bot.message_handler(commands=["publish"])
def publish(m):
    if not is_owner(m.from_user.id):
        bot.reply_to(m, "❌ У вас нет прав для публикации стартового окна.")
        return

    try:
        send_start_window(CHANNEL_USERNAME)
    except Exception as exc:
        bot.reply_to(m, f"❌ Не удалось опубликовать стартовое окно: {exc}")
        return

    bot.send_message(
        m.chat.id,
        "Стартовое окно опубликовано в канале. Закрепи его вручную.",
    )


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


@bot.message_handler(func=lambda msg: msg.text == "Очистить")
def cmd_clear(msg):
    if not ensure_verified(msg.chat.id, msg.from_user.id, force_check=True):
        return

    clear_history(msg.chat.id)
    user_histories.pop(msg.chat.id, None)
    user_messages.pop(msg.chat.id, None)
    user_test_modes.pop(msg.chat.id, None)

    send_and_store(msg.chat.id, "🧹 История диалога очищена", reply_markup=main_menu())


@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith("Lang"))
def cmd_language(msg):
    if not ensure_verified(msg.chat.id, msg.from_user.id, force_check=True):
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru"))
    kb.add(types.InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"))
    kb.add(types.InlineKeyboardButton("中文 🇨🇳", callback_data="lang_zh"))

    bot.send_message(msg.chat.id, "🌐 Choose your language:", reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
def on_language_change(call):
    if not ensure_verified(call.message.chat.id, call.from_user.id, force_check=True):
        bot.answer_callback_query(call.id, "❌ Требуется подписка")
        return

    lang = call.data.split("_", 1)[1]
    set_language(call.message.chat.id, lang)

    names = {"ru": "Русский 🇷🇺", "en": "English 🇬🇧", "zh": "中文 🇨🇳"}
    chosen = names.get(lang, lang)
    bot.answer_callback_query(call.id, f"Language set: {chosen}")
    send_and_store(call.message.chat.id, f"✅ Now I will talk in {chosen}", reply_markup=main_menu())

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
        get_info_text(),
        reply_markup=info_keyboard(),
    )
    send_and_store(
        m.chat.id,
        "Выбери тариф 👇",
        reply_markup=pay_menu()
    )


@bot.message_handler(
    func=lambda msg: msg.text in [
        "Созвучие • иконки — 299 ₽",
        "Отражение • аватарки — 999 ₽",
        "Путешествие • истории и фоны — 1999 ₽",
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


@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def callback_back_to_menu(call):
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
    _reward, msg = activate_tariff(m.chat.id, tariff_key)
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
            for chat_id in iter_history_chat_ids():
                clear_history(chat_id)
            print("🧹 История всех пользователей и сообщения очищены")

        counter += 1
        time.sleep(86400)  # раз в сутки

# --- Тестовые режимы ---
@bot.message_handler(commands=["testmodes"])
def test_modes_menu(m):
    if not ensure_verified(m.chat.id, m.from_user.id, force_check=True):
        return

    kb = types.InlineKeyboardMarkup(row_width=1)
    for title in TEST_BUTTONS:
        emoji, mode_key = TEST_BUTTON_CONFIG[title]
        kb.add(
            types.InlineKeyboardButton(
                f"{emoji} {title} (2 сообщения)",
                callback_data=f"test_{mode_key}",
            )
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
    if call.message.chat.id not in user_test_mode_usage:
        user_test_mode_usage[call.message.chat.id] = {
            "short_friend": 0,
            "philosopher": 0,
            "academic": 0,
        }
        user_test_modes[call.message.chat.id] = "academic"

    if user_test_mode_usage[call.message.chat.id][mode_key] >= 2:
        bot.answer_callback_query(call.id, "❌ Лимит 2 сообщений в этом режиме исчерпан.")
        return

    bot.answer_callback_query(call.id, f"✅ Пробный режим {MODES[mode_key]['name']} активирован!")
    bot.send_message(call.message.chat.id, f"Спроси меня что-то в режиме <b>{MODES[mode_key]['name']}</b> 👇")

    # фиксируем, что активный тестовый режим запущен
    clear_history(call.message.chat.id)
    user_histories[call.message.chat.id] = []
    user_test_mode_usage[call.message.chat.id][mode_key] += 1
    user_test_modes[call.message.chat.id] = mode_key

# --- fallback — если текст не совпал с меню, отправляем в GPT ---
@bot.message_handler(func=lambda msg: True)
def fallback(m):
    if not check_limit(m.chat.id): return
    increment_counter(m.chat.id)
    # обработка активного тестового режима
    mode_key = user_test_modes.get(m.chat.id)
    if mode_key and mode_key in user_test_mode_usage.get(m.chat.id, {}):
        if user_test_mode_usage[m.chat.id][mode_key] < 2:
            stream_gpt_answer(m.chat.id, m.text, mode_key)
            user_test_mode_usage[m.chat.id][mode_key] += 1
            if user_test_mode_usage[m.chat.id][mode_key] >= 2:
                user_test_modes.pop(m.chat.id, None)
            return
        else:
            user_test_modes.pop(m.chat.id, None)

    mode = get_user_mode(m.chat.id)
    stream_gpt_answer(m.chat.id, m.text, mode)

# --- Запуск ---
if __name__ == "__main__":
    from worker_media import start_media_worker
    from worker_payments import start_payments_worker

    start_media_worker()
    start_payments_worker()
    threading.Thread(target=background_checker, daemon=True).start()

    try:
        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=60,
            skip_pending=True,
        )
    except Exception as e:
        print("CRITICAL: polling crashed:", e)
        raise



