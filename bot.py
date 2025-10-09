import logging
import re
import sys
import threading
import time
import traceback
from contextlib import suppress
from pathlib import Path
from threading import Lock

from storage import (
    init_db,
    clear_history,
    iter_history_chat_ids,
    load_history,
    save_history,
    r,
    TTL,
)
from telebot import types
from telebot.apihelper import ApiTelegramException

# Ensure media handlers are registered
import media
from media import multimedia_menu

# Register web search handlers (command /web)
import handlers.web  # noqa: F401 - регистрация хендлеров через импорт

from internet import ask_gpt_web, should_escalate_to_web, should_prefer_web

from bot_utils import show_typing

# --- RU-only links mapping: ONLY for final user-visible text (do not touch SDK objects) ---
def map_links_ru(text):
    """
    Безопасная фильтрация ссылок: оставляем российские домены,
    заменяем зарубежные на доступные для РФ источники.
    """
    if not isinstance(text, str) or "http" not in text:
        return text
    rules = [
        (r'https?://(?:www\.)?weather\.com[^\s)]+', 'https://yandex.ru/pogoda'),
        (r'https?://(?:en\.)?wikipedia\.org[^\s)]+', 'https://ru.wikipedia.org'),
        (r'https?://(?:www\.)?google\.com[^\s)]+',  'https://yandex.ru'),
        (r'https?://(?:www\.)?bbc\.com[^\s)]+',     'https://tass.ru'),
        (r'https?://(?:www\.)?cnn\.com[^\s)]+',     'https://ria.ru'),
    ]
    for pat, repl in rules:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    return text

# --- Конфиг: значения централизованы в settings.py ---
from settings import (
    bot,
    client,
    CHAT_MODEL,
    HISTORY_LIMIT,
    OWNER_ID,
    is_owner,
    SYSTEM_PROMPT,
)
from openai_adapter import (
    extract_response_text,
    prepare_responses_input,
)
from text_utils import sanitize_for_telegram, sanitize_model_output

# Регистрация команд автопостинга
import auto_post  # noqa: F401 - регистрация хендлеров автопостинга при импорте

from usage_tracker import (
    compose_display_name,
    format_usage_report,
    format_user_stats,
    init_usage_tracking,
    record_user_activity,
)

# Initialize the SQLite storage before handling any requests
init_db()
init_usage_tracking()


def _register_bot_commands() -> None:
    """Отобразить основные команды в боковом меню Telegram."""

    owner_commands = [
        types.BotCommand("post_short", "Короткий пост"),
        types.BotCommand("post_long", "Длинный пост"),
        types.BotCommand("post_news", "Новость с фото"),
        types.BotCommand("top_users", "Топ активных пользователей"),
        types.BotCommand("user_stats", "Статистика по ID"),
    ]

    try:
        with suppress(Exception):
            bot.delete_my_commands(scope=types.BotCommandScopeDefault())
            default_menu_cls = getattr(types, "MenuButtonDefault", None)
            if default_menu_cls:
                bot.set_chat_menu_button(menu_button=default_menu_cls())
            else:
                bot.set_chat_menu_button()
        bot.set_my_commands(
            owner_commands,
            scope=types.BotCommandScopeChat(chat_id=OWNER_ID),
        )
        menu_button_cls = getattr(types, "MenuButtonCommands", None)
        if menu_button_cls:
            bot.set_chat_menu_button(chat_id=OWNER_ID, menu_button=menu_button_cls())
    except Exception:
        pass


_register_bot_commands()

# --- Логирование с записью в файл ---
LOG_FILE = Path(__file__).resolve().parent / "gpsbot.log"

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def log_exception(exc: Exception) -> None:
    """Log unexpected polling exceptions both to stdout and a file."""
    tb = traceback.format_exc()
    msg = f"CRITICAL: polling crashed: {exc}\n{tb}"
    print(msg)
    logging.error(msg)
    sys.stdout.flush()


# --- Константы подписки ---
CHANNEL_USERNAME = "AI Systems"
CHANNEL_LINK = "https://t.me/SynteraAI"
CHANNEL_CHAT_ID = "@SynteraAI"
GROUP_NAME = "Hubconsult"
GROUP_LINK = "https://t.me/HubConsult"
GROUP_CHAT_ID = "@HubConsult"
BOT_DEEP_LINK = "https://t.me/SynteraGPT_bot"
PHOTO_FILE = Path(__file__).resolve().parent / "baner_dlya_perehoda.png"
START_CAPTION = (
    "<b>SynteraGPT</b>\n\n"
    "Чат-бот с выходом в интернет: найдёт, проверит и объяснит.\n\n"
    "Возможности:\n"
    "— Поиск и проверка фактов онлайн\n"
    "— GPT-5 интеллект и поддержка 24/7\n"
    "— Анализ фото и документов\n"
    "— Короткие и развёрнутые ответы\n\n"
    "🔥 Бесплатный доступ к продвинутым технологиям — попробуй все форматы и оцени возможности.\n\n"
    "Перед использованием подпишись на канал AI Systems и вступи в сообщество Hubconsult."
)

REQUIRED_CHATS = (
    {"id": CHANNEL_CHAT_ID, "title": CHANNEL_USERNAME, "link": CHANNEL_LINK},
    {"id": GROUP_CHAT_ID, "title": GROUP_NAME, "link": GROUP_LINK},
)
SUBSCRIPTION_PROMPT_COOLDOWN = 30
_subscription_prompted: dict[int, float] = {}

SUBSCRIPTION_MESSAGE = (
    "<b>Доступ к SynteraGPT</b>\n\n"
    "Перед использованием подпишись на канал AI Systems и вступи в группу Hubconsult. "
    "После подписки нажми \"Проверить подписку\"."
)


def _fetch_subscription_status(user_id: int) -> bool:
    for chat in REQUIRED_CHATS:
        try:
            member = bot.get_chat_member(chat["id"], user_id)
        except ApiTelegramException:
            return False

        status = getattr(member, "status", None)
        if status not in {"creator", "administrator", "member", "owner"}:
            return False

    return True


def _send_subscription_prompt(chat_id: int, *, force: bool = False) -> None:
    now = time.time()
    last_prompt = _subscription_prompted.get(chat_id, 0)
    if not force and now - last_prompt < SUBSCRIPTION_PROMPT_COOLDOWN:
        return

    _subscription_prompted[chat_id] = now

    kb = types.InlineKeyboardMarkup(row_width=1)
    for chat in REQUIRED_CHATS:
        kb.add(
            types.InlineKeyboardButton(
                f"Подписаться: {chat['title']}",
                url=chat["link"],
            )
        )

    kb.add(types.InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_subscription"))

    bot.send_message(chat_id, SUBSCRIPTION_MESSAGE, parse_mode="HTML", reply_markup=kb)


def ensure_subscription(chat_id: int, user_id: int | None = None, *, notify: bool = True) -> bool:
    uid = user_id or chat_id

    if is_owner(uid):
        return True

    status = _fetch_subscription_status(uid)

    if status:
        _subscription_prompted.pop(chat_id, None)
        return True

    if notify:
        _send_subscription_prompt(chat_id, force=True)
    return False


def _display_name_from_user(user) -> str:
    if user is None:
        return ""

    return compose_display_name(
        username=getattr(user, "username", None),
        first_name=getattr(user, "first_name", None),
        last_name=getattr(user, "last_name", None),
    )


# --- Хранилища состояния пользователей ---
# Хранилище истории сообщений пользователей (локальный кэш)
user_histories = {}  # {chat_id: [ {role: "user"/"assistant", content: "..."}, ... ]}
user_messages = {}  # {chat_id: [message_id, ...]}

# кеш выбранного языка (для офлайн-режима, если Redis недоступен)
_language_cache: dict[int, str] = {}

# --- Кэш ответов ---
# Сохраняет последние ответы: ключ (chat_id, text_lower) -> ответ.
response_cache: dict[tuple[int, str], str] = {}


def _ensure_history_cached(chat_id: int) -> None:
    if chat_id not in user_histories:
        past = load_history(chat_id)
        if past:
            user_histories[chat_id] = past
        else:
            user_histories[chat_id] = []


def send_start_window(chat_id) -> None:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Открыть бота", url=BOT_DEEP_LINK))

    try:
        with PHOTO_FILE.open("rb") as photo:
            bot.send_photo(
                chat_id,
                photo,
                caption=START_CAPTION,
                reply_markup=kb,
                parse_mode="HTML",
            )
    except FileNotFoundError:
        bot.send_message(
            chat_id,
            START_CAPTION,
            reply_markup=kb,
            parse_mode="HTML",
        )


# --- /media
@bot.message_handler(commands=["media"])
def cmd_media(m):
    if not ensure_subscription(m.chat.id, getattr(m.from_user, "id", None)):
        return
    bot.send_message(
        m.chat.id,
        "Доступные мультимедиа функции:",
        reply_markup=multimedia_menu(),
    )


# --- /profile
@bot.message_handler(commands=["profile"])
def cmd_profile(m):
    if not ensure_subscription(m.chat.id, getattr(m.from_user, "id", None)):
        return
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
    send_and_store(
        chat_id,
        START_CAPTION,
        reply_markup=main_menu(),
        parse_mode="HTML",
    )

# --- Клавиатуры ---

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("Медиа"),
        types.KeyboardButton("Профиль"),
    )
    kb.add(
        types.KeyboardButton("Очистить"),
        types.KeyboardButton("Lang 🌐"),
    )
    return kb


@bot.message_handler(func=lambda m: m.text == "Профиль")
def show_profile(m):
    cmd_profile(m)


@bot.message_handler(func=lambda m: m.text == "Медиа")
def show_media(m):
    cmd_media(m)

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

# --- Получение режима пользователя ---

def get_user_mode(chat_id: int) -> str:
    if is_owner(chat_id):
        return "philosopher"
    return "short_friend"

# --- Режимы общения ---

MODES = {
    "short_friend": {
        "name": "Короткий друг",
        # Новый промпт: друг отвечает на вопросы дружелюбно и честно,
        # не задаёт лишних вопросов и не ссылается на внешние источники.
        "system_prompt": (
            "Представь, что ты мой друг и помощник. Я буду делиться событиями и "
            "задавать вопросы, а ты отвечай честно, дружелюбно и поддерживающе. "
            "При необходимости давай информативные ответы на мои вопросы. Не вставляй "
            "ссылок на внешние источники и не повторяй один и тот же вопрос."
        ),
    },
    "philosopher": {
        "name": "Философ",
        # Новый промпт: философ отвечает глубоко, но своими словами,
        # не ссылаясь на интернет и не отказываясь от ответа.
        "system_prompt": (
            "Представь, что ты мудрый философ. Я буду задавать вопросы о жизни и мире. "
            "Ты отвечай, исследуя концепции и теории, предлагай глубокие размышления "
            "и новые идеи, но без ссылок на внешние ресурсы. Даже если тема сложна, "
            "дай свой ответ, опираясь на знания и логику."
        ),
    },
    "academic": {
        "name": "Академический",
        # Новый промпт: преподаватель объясняет темы ясно и структурированно,
        # не отправляя пользователя искать информацию на сторону.
        "system_prompt": (
            "Представь, что ты преподаватель и наставник. На мои вопросы отвечай "
            "ясно, структурированно и аргументированно, используя известные знания и "
            "примеры. Помоги понять сложные темы, разбивая их на более простые части. "
            "Не вставляй ссылки на внешние источники и не отказывайся от ответа."
        ),
    },
}

# --- Размер контекста для модели ---
# Сколько последних сообщений из истории отправлять в GPT.
CONTEXT_MESSAGES = 4

# Статический словарь блокировок по chat_id — предотвращает параллельные стримы в одном чате.
_chat_locks: dict[int, Lock] = {}
_logger = logging.getLogger("synteragpt.stream")
_logger.setLevel(logging.INFO)
Path("/root/SynteraGPT/logs").mkdir(parents=True, exist_ok=True)
# настроим простой file handler (по желанию)
fh = logging.FileHandler("/root/SynteraGPT/logs/stream_gpt.log")
fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
_logger.addHandler(fh)



def ask_gpt(messages, max_tokens=None):
    """
    Главная функция вызова OpenAI SDK.
    1. Сначала пробуем Responses API с tools (web-search, file-search и т.д.)
    2. Если не доступно — fallback в Chat Completions.
    """
    try:
        # --- Responses API (с поддержкой web_search tools) ---
        inputs = prepare_responses_input(messages)
        resp = client.responses.create(
            model=inputs.get("model"),
            input=inputs.get("input"),
            temperature=inputs.get("temperature", 0.3),
            max_output_tokens=max_tokens or inputs.get("max_output_tokens"),
            tools=inputs.get("tools"),
            tool_choice=inputs.get("tool_choice"),
        )
        text = extract_response_text(resp)
        if isinstance(text, str) and text.strip():
            # применяем фильтр ссылок только к готовому тексту
            return map_links_ru(text.strip())
    except Exception:
        pass

    # --- fallback: Chat Completions ---
    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            response_format={"type": "text"},
        )
        text = extract_response_text(resp)
        if isinstance(text, str) and text.strip():
            return map_links_ru(text.strip())
    except Exception:
        pass

    return "Извините, не удалось получить ответ."

def _get_chat_lock(chat_id: int) -> Lock:
    """Возвращает (и создаёт при необходимости) Lock для конкретного чата."""
    lock = _chat_locks.get(chat_id)
    if lock is None:
        lock = Lock()
        _chat_locks[chat_id] = lock
    return lock


def stream_gpt_answer(
    chat_id: int,
    user_text: str,
    mode_key: str = "short_friend",
    *,
    force_web: bool = False,
    allow_web_fallback: bool = False,
) -> None:
    """Stream a GPT-5 mini answer and optionally fall back to web search."""

    lock = _get_chat_lock(chat_id)
    if not lock.acquire(blocking=False):
        with suppress(Exception):
            bot.send_message(chat_id, "⚠️ Уже формируется ответ в этом чате. Подождите, пожалуйста.")
        return

    try:
        _ensure_history_cached(chat_id)

        history = user_histories.setdefault(chat_id, [])
        history.append({"role": "user", "content": user_text})

        language = get_language(chat_id)
        mode_prompt = MODES[mode_key]["system_prompt"]
        system_prompt = (
            f"{SYSTEM_PROMPT}\n\n{mode_prompt}\n\nОтвечай на языке пользователя: {language}."
        )
        context_history = history[-CONTEXT_MESSAGES:]
        messages = [{"role": "system", "content": system_prompt}] + context_history

        cache_key = (chat_id, user_text.strip().lower())
        use_cache = not force_web
        cached = response_cache.get(cache_key) if use_cache else None
        if cached:
            show_typing(chat_id)
            draft = bot.send_message(chat_id, "…", reply_markup=main_menu())
            msg_id = draft.message_id
            safe_cached = sanitize_for_telegram(cached)
            try:
                bot.edit_message_text(safe_cached or cached, chat_id, msg_id, parse_mode="HTML")
            except Exception:
                with suppress(Exception):
                    bot.send_message(chat_id, safe_cached or cached, parse_mode="HTML")
            history.append({"role": "assistant", "content": cached})
            trimmed = history[-HISTORY_LIMIT:]
            user_histories[chat_id] = trimmed
            with suppress(Exception):
                save_history(chat_id, trimmed)
            return

        show_typing(chat_id)
        draft = bot.send_message(chat_id, "…", reply_markup=main_menu())
        msg_id = draft.message_id
        message_failed = False

        if force_web:
            try:
                web_raw = ask_gpt_web(user_text).strip()
            except Exception:
                if history and history[-1].get("role") == "user" and history[-1].get("content") == user_text:
                    history.pop()
                failure_text = "⚠️ Не удалось получить ответ. Попробуйте ещё раз позже."
                safe_failure = sanitize_for_telegram(failure_text)
                try:
                    bot.edit_message_text(safe_failure or failure_text, chat_id, msg_id, parse_mode="HTML")
                except Exception:
                    with suppress(Exception):
                        bot.send_message(chat_id, safe_failure or failure_text, parse_mode="HTML")
                return

            final_text = sanitize_model_output(web_raw)
            if not final_text:
                final_text = "😔 Не удалось найти информацию. Попробуй уточнить запрос."

            safe_text = sanitize_for_telegram(final_text)
            try:
                bot.edit_message_text(safe_text or final_text, chat_id, msg_id, parse_mode="HTML")
            except Exception:
                with suppress(Exception):
                    bot.send_message(chat_id, safe_text or final_text, parse_mode="HTML")

            history.append({"role": "assistant", "content": final_text})
            trimmed_history = history[-HISTORY_LIMIT:]
            user_histories[chat_id] = trimmed_history
            try:
                save_history(chat_id, trimmed_history)
            except Exception:
                _logger.exception("Failed to persist chat history")

            response_cache[cache_key] = final_text
            return

        try:
            final_text = ask_gpt(messages)
            error_occurred = False
        except Exception:
            final_text = ""
            error_occurred = True
            _logger.exception("Failed to get response")

        if error_occurred:
            if history and history[-1].get("role") == "user" and history[-1].get("content") == user_text:
                history.pop()
            failure_text = "⚠️ Не удалось получить ответ. Попробуйте ещё раз позже."
            safe_failure = sanitize_for_telegram(failure_text)
            if not message_failed:
                try:
                    bot.edit_message_text(safe_failure or failure_text, chat_id, msg_id, parse_mode="HTML")
                except Exception:
                    message_failed = True
            if message_failed:
                with suppress(Exception):
                    bot.send_message(chat_id, safe_failure or failure_text, parse_mode="HTML")
            return

        final_text = sanitize_model_output(final_text)

        used_web = False
        if allow_web_fallback and should_escalate_to_web(user_text, final_text):
            try:
                if not message_failed:
                    try:
                        bot.edit_message_text(
                            "🌐 Ищу свежие данные…", chat_id, msg_id, parse_mode="HTML"
                        )
                    except Exception:
                        message_failed = True
                web_raw = ask_gpt_web(user_text).strip()
            except Exception:
                web_raw = ""

            if web_raw:
                new_final = sanitize_model_output(web_raw)
                if new_final:
                    final_text = new_final
                    used_web = True

        if not final_text:
            final_text = "⚠️ Ответ пуст."

        final_text = map_links_ru(final_text)

        if used_web:
            response_cache.pop(cache_key, None)

        safe_text = sanitize_for_telegram(final_text)
        if not message_failed:
            try:
                bot.edit_message_text(safe_text or final_text, chat_id, msg_id, parse_mode="HTML")
            except Exception:
                message_failed = True
        if message_failed:
            with suppress(Exception):
                bot.send_message(chat_id, safe_text or final_text, parse_mode="HTML")

        history.append({"role": "assistant", "content": final_text})
        trimmed_history = history[-HISTORY_LIMIT:]
        user_histories[chat_id] = trimmed_history
        try:
            save_history(chat_id, trimmed_history)
        except Exception:
            _logger.exception("Failed to persist chat history")

        response_cache[cache_key] = final_text

    finally:
        with suppress(Exception):
            lock.release()

# --- Хэндлеры ---
@bot.message_handler(commands=["start"])
def start(m):
    if not ensure_subscription(m.chat.id, getattr(m.from_user, "id", None)):
        return
    send_welcome_menu(m.chat.id)


@bot.message_handler(commands=["publish"])
def publish(m):
    if not is_owner(m.from_user.id):
        bot.reply_to(m, "❌ У вас нет прав для публикации стартового окна.")
        return

    try:
        send_start_window(CHANNEL_CHAT_ID)
    except Exception as exc:
        bot.reply_to(m, f"❌ Не удалось опубликовать стартовое окно: {exc}")
        return

    bot.send_message(
        m.chat.id,
        "Стартовое окно опубликовано в канале. Закрепи его вручную.",
    )


@bot.message_handler(func=lambda msg: msg.text == "Очистить")
def cmd_clear(msg):
    if not ensure_subscription(msg.chat.id, getattr(msg.from_user, "id", None)):
        return
    clear_history(msg.chat.id)
    user_histories.pop(msg.chat.id, None)
    user_messages.pop(msg.chat.id, None)

    send_and_store(msg.chat.id, "🧹 История диалога очищена", reply_markup=main_menu())


@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith("Lang"))
def cmd_language(msg):
    if not ensure_subscription(msg.chat.id, getattr(msg.from_user, "id", None)):
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru"))
    kb.add(types.InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"))
    kb.add(types.InlineKeyboardButton("中文 🇨🇳", callback_data="lang_zh"))

    bot.send_message(msg.chat.id, "🌐 Choose your language:", reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def on_subscription_check(call):
    subscribed = ensure_subscription(
        call.message.chat.id,
        getattr(call.from_user, "id", None),
        notify=False,
    )
    if subscribed:
        bot.answer_callback_query(call.id, "✅ Подписка подтверждена!")
        send_welcome_menu(call.message.chat.id)
    else:
        bot.answer_callback_query(
            call.id,
            "⚠️ Подписка не найдена. Проверьте, что вы подписаны на оба сообщества.",
            show_alert=False,
        )
        _send_subscription_prompt(call.message.chat.id, force=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
def on_language_change(call):
    if not ensure_subscription(call.message.chat.id, getattr(call.from_user, "id", None)):
        bot.answer_callback_query(call.id, "Сначала подпишитесь на канал и группу")
        return
    lang = call.data.split("_", 1)[1]
    set_language(call.message.chat.id, lang)

    names = {"ru": "Русский 🇷🇺", "en": "English 🇬🇧", "zh": "中文 🇨🇳"}
    chosen = names.get(lang, lang)
    bot.answer_callback_query(call.id, f"Language set: {chosen}")
    send_and_store(call.message.chat.id, f"✅ Now I will talk in {chosen}", reply_markup=main_menu())


@bot.message_handler(commands=["top_users"])
def show_top_users(m):
    if not is_owner(getattr(m.from_user, "id", 0)):
        bot.reply_to(m, "❌ Команда доступна только владельцу бота.")
        return

    if not ensure_subscription(m.chat.id, getattr(m.from_user, "id", None)):
        return

    report = format_usage_report()
    bot.send_message(m.chat.id, report, parse_mode="HTML")


@bot.message_handler(commands=["user_stats"])
def show_user_stats(m):
    if not is_owner(getattr(m.from_user, "id", 0)):
        bot.reply_to(m, "❌ Команда доступна только владельцу бота.")
        return

    if not ensure_subscription(m.chat.id, getattr(m.from_user, "id", None)):
        return

    target_id = None
    hint_name = ""

    parts = (m.text or "").split(maxsplit=1)
    if len(parts) > 1:
        candidate = parts[1].strip()
        candidate = candidate.replace("@", "")
        if candidate.isdigit():
            target_id = int(candidate)
        else:
            bot.reply_to(m, "⚠️ Укажите ID пользователя цифрами или ответьте на его сообщение.")
            return
    elif m.reply_to_message:
        target_user = getattr(m.reply_to_message, "from_user", None)
        if target_user:
            target_id = getattr(target_user, "id", None)
            hint_name = _display_name_from_user(target_user)

    if not target_id:
        bot.reply_to(m, "⚠️ Укажите ID пользователя или ответьте на сообщение нужного пользователя.")
        return

    report = format_user_stats(target_id, hint_name)
    bot.send_message(m.chat.id, report, parse_mode="HTML")

# --- Фоновая проверка окончаний подписок и очистка истории ---
def background_checker():
    counter = 1
    while True:
        if counter % 7 == 0:
            # Очищаем локальные хранилища: историю сообщений, кэш ответов и отправленные сообщения
            user_histories.clear()
            response_cache.clear()
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

# --- fallback — если текст не совпал с меню, отправляем в GPT ---
@bot.message_handler(
    func=lambda msg: bool(getattr(msg, "text", "")) and not msg.text.startswith("/")
)
def fallback(m):
    if not ensure_subscription(m.chat.id, getattr(m.from_user, "id", None)):
        return
    user = getattr(m, "from_user", None)
    user_id = getattr(user, "id", m.chat.id)
    record_user_activity(
        user_id,
        category="text",
        display_name=_display_name_from_user(user),
    )
    mode = get_user_mode(m.chat.id)
    prefer_web = should_prefer_web(m.text)
    stream_gpt_answer(
        m.chat.id,
        m.text,
        mode,
        force_web=prefer_web,
        allow_web_fallback=not prefer_web,
    )

# --- Запуск ---
if __name__ == "__main__":
    from worker_media import start_media_worker

    start_media_worker()
    threading.Thread(target=background_checker, daemon=True).start()

    while True:
        try:
            bot.polling(
                none_stop=True,
                timeout=60,
                long_polling_timeout=60,
                skip_pending=True,
            )
        except Exception as exc:  # noqa: BLE001 - хотим логировать любые сбои
            log_exception(exc)



