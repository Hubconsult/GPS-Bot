from bot_utils import show_typing
from internet import ask_gpt_web
from settings import bot
from telebot import util as telebot_util

from usage_tracker import compose_display_name, record_user_activity

# Состояние: ждём ли запрос от пользователя
_web_mode = {}  # {chat_id: True/False}


def _sanitize_answer(text: str) -> str:
    cleaned = (text or "").replace("<think>", "").replace("</think>", "")
    cleaned = cleaned.replace("<reasoning>", "").replace("</reasoning>", "")
    cleaned = cleaned.replace("\x00", "")
    return telebot_util.escape(cleaned)


def _ensure_subscription(message) -> bool:
    from bot import ensure_subscription

    user_id = getattr(message.from_user, "id", None)
    return ensure_subscription(message.chat.id, user_id)


@bot.message_handler(commands=["web"])
def cmd_web(m):
    if not _ensure_subscription(m):
        return
    _web_mode[m.chat.id] = True
    bot.send_message(m.chat.id, "🔎 Что найти в интернете? Напиши запрос одной строкой.")


@bot.message_handler(func=lambda msg: _web_mode.get(msg.chat.id) is True)
def handle_web_query(m):
    if not _ensure_subscription(m):
        _web_mode.pop(m.chat.id, None)
        return

    query = (m.text or "").strip()
    if not query:
        bot.send_message(m.chat.id, "❌ Пустой запрос. Напиши вопрос или ключевые слова.")
        return

    user = getattr(m, "from_user", None)
    user_id = getattr(user, "id", m.chat.id)
    record_user_activity(
        user_id,
        category="text",
        display_name=compose_display_name(
            username=getattr(user, "username", None),
            first_name=getattr(user, "first_name", None),
            last_name=getattr(user, "last_name", None),
        ),
    )
    show_typing(m.chat.id)
    try:
        answer = ask_gpt_web(query).strip()
    except Exception:
        bot.send_message(m.chat.id, "😔 Не удалось получить ответ. Попробуй ещё раз позже.")
        _web_mode.pop(m.chat.id, None)
        return

    if not answer:
        bot.send_message(m.chat.id, "😔 Не удалось найти информацию. Попробуй уточнить запрос.")
        _web_mode.pop(m.chat.id, None)
        return

    bot.send_message(m.chat.id, _sanitize_answer(answer), parse_mode="HTML")
    _web_mode.pop(m.chat.id, None)
