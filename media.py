import base64
import io
import requests
from telebot import types

from settings import bot, client, TOKEN, IMAGE_MODEL, VISION_MODEL
from usage_tracker import compose_display_name, record_user_activity
from worker_media import enqueue_media_task

# Состояние простое: что от пользователя ждём далее
user_media_state = {}   # {chat_id: {"mode": "photo_gen"/"photo_analyze"/"pdf"/"excel"/"pptx"}}

# --- Меню мультимедиа ---

def multimedia_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("Фото", callback_data="mm_photo_gen"),
        types.InlineKeyboardButton("Анализ фото", callback_data="mm_photo_ana"),
        types.InlineKeyboardButton("PDF", callback_data="mm_pdf"),
        types.InlineKeyboardButton("Excel", callback_data="mm_excel"),
        types.InlineKeyboardButton("Презентация", callback_data="mm_pptx"),
    )
    return kb
# --- Точка входа из главного меню: команда «Медиа» ---

def _display_name(user) -> str:
    return compose_display_name(
        username=getattr(user, "username", None),
        first_name=getattr(user, "first_name", None),
        last_name=getattr(user, "last_name", None),
    )


@bot.message_handler(func=lambda msg: msg.text == "Медиа")
def open_multimedia(m):
    bot.send_message(m.chat.id, "Выбери функцию:", reply_markup=multimedia_menu())

# --- Ветки функций ---

@bot.callback_query_handler(func=lambda call: call.data == "mm_photo_gen")
def on_photo_gen(call):
    bot.answer_callback_query(call.id)
    user_media_state[call.message.chat.id] = {"mode": "photo_gen"}
    bot.send_message(call.message.chat.id, "Опиши картинку, которую хочешь получить:")

@bot.callback_query_handler(func=lambda call: call.data == "mm_photo_ana")
def on_photo_analyze(call):
    bot.answer_callback_query(call.id)
    user_media_state[call.message.chat.id] = {"mode": "photo_analyze"}
    bot.send_message(call.message.chat.id, "Пришли фото сообщением, я опишу и проанализирую его.")

@bot.callback_query_handler(func=lambda call: call.data == "mm_pdf")
def on_pdf(call):
    bot.answer_callback_query(call.id)
    user_media_state[call.message.chat.id] = {"mode": "pdf"}
    bot.send_message(call.message.chat.id, "Пришли текст для PDF (каждая строка будет перенесена).")

@bot.callback_query_handler(func=lambda call: call.data == "mm_excel")
def on_excel(call):
    bot.answer_callback_query(call.id)
    user_media_state[call.message.chat.id] = {"mode": "excel"}
    bot.send_message(call.message.chat.id, "Пришли данные в виде CSV-подобного текста:\nЗаголовок1, Заголовок2\nЗначение1, Значение2")

@bot.callback_query_handler(func=lambda call: call.data == "mm_pptx")
def on_pptx(call):
    bot.answer_callback_query(call.id)
    user_media_state[call.message.chat.id] = {"mode": "pptx"}
    bot.send_message(call.message.chat.id, "Пришли план слайдов:\nЗаголовок: Первый слайд\n- Пункт 1\n- Пункт 2\n===\nЗаголовок: Второй слайд\n- Пункт A")

# --- Обработка текстов для режимов photo_gen/pdf/excel/pptx ---

@bot.message_handler(func=lambda msg: user_media_state.get(msg.chat.id, {}).get("mode") in ("photo_gen","pdf","excel","pptx"))
def media_text_router(m):
    state = user_media_state.get(m.chat.id, {})
    mode = state.get("mode")
    if mode == "photo_gen":
        # генерация фото
        prompt = m.text.strip()
        record_user_activity(
            getattr(m.from_user, "id", m.chat.id),
            category="image",
            display_name=_display_name(m.from_user),
        )
        try:
            result = client.images.generate(
                model=IMAGE_MODEL,
                prompt=prompt,
                size="1024x1024",
                quality="standard",
            )
            b64 = result.data[0].b64_json
            img_bytes = base64.b64decode(b64)
            bot.send_photo(m.chat.id, photo=io.BytesIO(img_bytes), caption="Готово ✅")
        except Exception as e:
            bot.send_message(m.chat.id, f"⚠️ Ошибка генерации: {e}")
        finally:
            user_media_state.pop(m.chat.id, None)
        return

    if mode == "pdf":
        record_user_activity(
            getattr(m.from_user, "id", m.chat.id),
            category="document",
            display_name=_display_name(m.from_user),
        )
        bot.send_message(m.chat.id, "📄 Готовлю PDF, пришлю файл чуть позже…")
        enqueue_media_task(m.chat.id, "pdf", m.text or "")
        user_media_state.pop(m.chat.id, None)
        return

    if mode == "excel":
        record_user_activity(
            getattr(m.from_user, "id", m.chat.id),
            category="document",
            display_name=_display_name(m.from_user),
        )
        bot.send_message(m.chat.id, "📊 Формирую Excel, отправлю, как только соберу данные…")
        enqueue_media_task(m.chat.id, "excel", m.text or "")
        user_media_state.pop(m.chat.id, None)
        return

    if mode == "pptx":
        record_user_activity(
            getattr(m.from_user, "id", m.chat.id),
            category="document",
            display_name=_display_name(m.from_user),
        )
        bot.send_message(m.chat.id, "🖼️ Собираю презентацию, скоро пришлю готовый файл…")
        enqueue_media_task(m.chat.id, "pptx", m.text or "")
        user_media_state.pop(m.chat.id, None)
        return

# --- Приём фото для анализа ---

@bot.message_handler(content_types=["photo"])
def on_photo_message(m):
    state = user_media_state.get(m.chat.id, {})
    if state.get("mode") != "photo_analyze":
        return  # не ждём фото — игнорируем, отработает общий fallback

    try:
        file_id = m.photo[-1].file_id
        file_info = bot.get_file(file_id)
        url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        img_resp = requests.get(url, timeout=30)
        img_resp.raise_for_status()
        img_b64 = base64.b64encode(img_resp.content).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{img_b64}"

        record_user_activity(
            getattr(m.from_user, "id", m.chat.id),
            category="text",
            display_name=_display_name(m.from_user),
        )

        # Vision-запрос
        resp = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Опиши и проанализируй это фото кратко и по делу."},
                    {"type": "input_image", "image_url": data_url}
                ]
            }],
        )
        text = resp.choices[0].message.content.strip()
        bot.send_message(m.chat.id, text or "Готово ✅")
    except Exception as e:
        bot.send_message(m.chat.id, f"⚠️ Ошибка анализа: {e}")
    finally:
        user_media_state.pop(m.chat.id, None)
