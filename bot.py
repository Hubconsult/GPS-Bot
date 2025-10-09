import logging
import re
import sys
import threading
import time
import traceback
from contextlib import suppress
from pathlib import Path
from threading import Lock
from typing import Callable

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

# Ensure media handlers are registered
import media
from media import multimedia_menu

# Register web search handlers (command /web)
import handlers.web  # noqa: F401 - регистрация хендлеров через импорт

from internet import ask_gpt_web, should_escalate_to_web, should_prefer_web

from bot_utils import show_typing

# --- Конфиг: значения централизованы в settings.py ---
from settings import (
    bot,
    client,
    CHAT_MODEL,
    HISTORY_LIMIT,
    is_owner,
    SYSTEM_PROMPT,
)
from openai_adapter import (
    coerce_content_to_text,
    extract_response_text,
    prepare_responses_input,
)
from text_utils import sanitize_for_telegram, sanitize_model_output

# Регистрация команды /post
import auto_post  # noqa: F401 - регистрация команды /post

# Initialize the SQLite storage before handling any requests
init_db()

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


def replace_foreign_links_with_ru(text: str) -> str:
    """Заменяет зарубежные ссылки (weather.com, wikipedia.org и т.д.) на российские аналоги."""
    replacements = {
        r"https?://(www\.)?weather\.com[^\s)]*": "https://yandex.ru/pogoda",
        r"https?://(en\.)?wikipedia\.org[^\s)]*": "https://ru.wikipedia.org",
        r"https?://(www\.)?cnn\.com[^\s)]*": "https://ria.ru",
        r"https?://(www\.)?bbc\.com[^\s)]*": "https://tass.ru",
        r"https?://(www\.)?google\.com[^\s)]*": "https://yandex.ru",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


# --- Константы подписки ---
CHANNEL_USERNAME = "@SynteraAI"
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
    "Присоединяйся к каналу @SynteraAI, чтобы не пропустить обновления."
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

# --- GPT-5 Mini ответ с потоковой выдачей ---

EDIT_INTERVAL = 0.4             # не слишком частые редактирования (сек)
FIRST_CHUNK_TOKENS = 12         # показать быстро несколько токенов
STREAM_STALL_TIMEOUT = 30.0     # увеличили с 12.0, даём стриму до 30 секунд тишины
MAX_RETRIES = 3                 # увеличили число попыток с 2 до 3
BACKOFF_BASE = 1.0              # базовая пауза при retry (сек)

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



def ask_gpt(
    messages: list[dict],
    *,
    max_tokens: int | None = None,
    tools: list[dict] | None = None,
    on_chunk: Callable[[str], None] | None = None,
) -> str:
    """Stream a response from the Responses API and optionally emit partial chunks."""

    kwargs: dict = {
        "model": CHAT_MODEL,
        "input": prepare_responses_input(messages),
        "stream": True,
    }
    if max_tokens is not None:
        kwargs["max_output_tokens"] = max_tokens
    if tools:
        kwargs["tools"] = tools

    stream = client.responses.create(**kwargs)
    collected: list[str] = []
    final_response = None

    try:
        for event in stream:
            event_type = getattr(event, "type", "")
            if event_type in {"response.output_text.delta", "response.message.delta"}:
                chunk = coerce_content_to_text(getattr(event, "delta", None))
                if chunk:
                    collected.append(chunk)
                    if on_chunk is not None:
                        try:
                            on_chunk(chunk)
                        except Exception:
                            pass
            elif event_type == "response.error":
                error = getattr(event, "error", None)
                message = getattr(error, "message", None) or str(error)
                raise RuntimeError(message)
            elif event_type == "response.completed":
                with suppress(Exception):
                    final_response = stream.get_final_response()

        if final_response is None:
            with suppress(Exception):
                final_response = stream.get_final_response()
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            with suppress(Exception):
                close()

    text = ""
    if final_response is not None:
        text = extract_response_text(final_response) or ""
    if not text:
        text = "".join(collected)
    return text.strip()

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

        partial_chunks: list[str] = []
        start_time = time.monotonic()
        last_edit = start_time
        first_chunk_sent = False

        def handle_chunk(chunk: str) -> None:
            nonlocal last_edit, first_chunk_sent, message_failed
            if not chunk:
                return

            partial_chunks.append(chunk)
            aggregated_raw = "".join(partial_chunks)
            safe_partial = sanitize_for_telegram(aggregated_raw)
            if not safe_partial:
                return

            now = time.monotonic()
            should_update = False
            if not first_chunk_sent:
                cleaned_length = len(sanitize_model_output(aggregated_raw))
                if cleaned_length >= FIRST_CHUNK_TOKENS or now - start_time >= EDIT_INTERVAL:
                    should_update = True
            elif now - last_edit >= EDIT_INTERVAL:
                should_update = True

            if should_update and not message_failed:
                try:
                    bot.edit_message_text(safe_partial, chat_id, msg_id, parse_mode="HTML")
                    first_chunk_sent = True
                    last_edit = now
                except Exception:
                    message_failed = True

        error_occurred = False
        try:
            final_text = ask_gpt(messages, on_chunk=handle_chunk)
        except Exception:
            error_occurred = True
            final_text = ""
            _logger.exception("Failed to stream response")

        aggregated_raw = "".join(partial_chunks)

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

        if not final_text:
            final_text = aggregated_raw

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

        final_text = replace_foreign_links_with_ru(final_text)

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
    send_welcome_menu(m.chat.id)


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


@bot.message_handler(func=lambda msg: msg.text == "Очистить")
def cmd_clear(msg):
    clear_history(msg.chat.id)
    user_histories.pop(msg.chat.id, None)
    user_messages.pop(msg.chat.id, None)

    send_and_store(msg.chat.id, "🧹 История диалога очищена", reply_markup=main_menu())


@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith("Lang"))
def cmd_language(msg):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru"))
    kb.add(types.InlineKeyboardButton("English 🇬🇧", callback_data="lang_en"))
    kb.add(types.InlineKeyboardButton("中文 🇨🇳", callback_data="lang_zh"))

    bot.send_message(msg.chat.id, "🌐 Choose your language:", reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
def on_language_change(call):
    lang = call.data.split("_", 1)[1]
    set_language(call.message.chat.id, lang)

    names = {"ru": "Русский 🇷🇺", "en": "English 🇬🇧", "zh": "中文 🇨🇳"}
    chosen = names.get(lang, lang)
    bot.answer_callback_query(call.id, f"Language set: {chosen}")
    send_and_store(call.message.chat.id, f"✅ Now I will talk in {chosen}", reply_markup=main_menu())

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
    text = (
        "Я работаю на базе GPT-5 Mini, новейшей компактной модели. "
        "GPT-5 Mini обеспечивает глубокую проработку диалога, высокую точность "
        "и адаптивность, опирается на академические знания и современные исследования. "
        "Модель поддерживает разные стили общения: Короткий друг, Философ и Академический. "
        "Она разработана для того, чтобы вести живой разговор, давать содержательные ответы "
        "и предлагать практические рекомендации на основе психологии. "
        "Использование GPT-5 Mini позволяет создавать осмысленные и развернутые ответы, "
        "которые помогают в самоанализе и принятии решений."
    )
    bot.send_message(m.chat.id, text, reply_markup=main_menu())

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



