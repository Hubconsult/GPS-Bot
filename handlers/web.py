from telebot import util as telebot_util

from bot_utils import show_typing
from internet import ask_gpt_web
from settings import bot

# Состояние: ждём ли запрос от пользователя
_web_mode = {}  # {chat_id: True/False}


def _sanitize_answer(text: str) -> str:
    cleaned = (text or "").replace("<think>", "").replace("</think>", "")
    cleaned = cleaned.replace("<reasoning>", "").replace("</reasoning>", "")
    cleaned = cleaned.replace("\x00", "")
    return telebot_util.escape(cleaned)


@bot.message_handler(commands=["web"])
def cmd_web(m):
    _web_mode[m.chat.id] = True
    bot.send_message(m.chat.id, "🔎 Что найти в интернете? Напиши запрос одной строкой.")


@bot.message_handler(func=lambda msg: _web_mode.get(msg.chat.id) is True)
def handle_web_query(m):
    query = (m.text or "").strip()
    if not query:
        bot.send_message(m.chat.id, "❌ Пустой запрос. Напиши вопрос или ключевые слова.")
        return

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
