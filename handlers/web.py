from telebot import types
from settings import bot
from internet.free_search import web_search_aggregate, format_sources

# Состояние: ждём ли запрос от пользователя
_web_mode = {}  # {chat_id: True/False}


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

    # 1. Ищем в интернете
    sources = web_search_aggregate(query)

    if not sources:
        bot.send_message(m.chat.id, "😔 Не смог найти надёжные источники. Попробуй по-другому.")
        _web_mode.pop(m.chat.id, None)
        return

    # 2. Формируем ответ
    src_text = format_sources(sources)
    answer_parts = [f"🌐 <b>Запрос:</b> {m.text}"]

    for s in sources:
        if s.get("snippet"):
            answer_parts.append(f"\n<b>{s['title']}</b>\n{s['snippet']}\n")

    answer = "\n".join(answer_parts) + f"\n\n<b>Источники:</b>\n{src_text}"

    bot.send_message(m.chat.id, answer, parse_mode="HTML", disable_web_page_preview=False)

    # Сбрасываем режим
    _web_mode.pop(m.chat.id, None)
