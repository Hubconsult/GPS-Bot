import base64
import io
import requests
from telebot import types
from openai import OpenAI

from settings import bot, client, TOKEN, IMAGE_MODEL, VISION_MODEL, \
    PAY_URL_PACK_PHOTO_50, PAY_URL_PACK_PHOTO_200, \
    PAY_URL_PACK_DOC_10, PAY_URL_PACK_DOC_30, \
    PAY_URL_PACK_ANALYZE_20, PAY_URL_PACK_ANALYZE_100
from tariffs import TARIFFS, user_tariffs
from storage import get_or_init_month_balance, dec_media, get_media_balance, \
                    read_trials, mark_trial_used, add_package
from media_utils import make_pdf, make_excel, make_pptx

# Состояние простое: что от пользователя ждём далее
user_media_state = {}   # {chat_id: {"mode": "photo_gen"/"photo_analyze"/"pdf"/"excel"/"pptx"}}

# --- Меню мультимедиа ---

def multimedia_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🖼 Генерация фото", callback_data="mm_photo_gen"),
        types.InlineKeyboardButton("🔍 Анализ фото", callback_data="mm_photo_ana"),
        types.InlineKeyboardButton("📑 PDF", callback_data="mm_pdf"),
        types.InlineKeyboardButton("📊 Excel", callback_data="mm_excel"),
        types.InlineKeyboardButton("🎞 Презентация", callback_data="mm_pptx"),
    )
    kb.add(types.InlineKeyboardButton("🧩 Докупить пакеты", callback_data="mm_buy"))
    return kb

def multimedia_buy_menu():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("📸 50 фото • 299 ₽", url=PAY_URL_PACK_PHOTO_50))
    kb.add(types.InlineKeyboardButton("📸 200 фото • 799 ₽", url=PAY_URL_PACK_PHOTO_200))
    kb.add(types.InlineKeyboardButton("📑 10 документов • 199 ₽", url=PAY_URL_PACK_DOC_10))
    kb.add(types.InlineKeyboardButton("📑 30 документов • 499 ₽", url=PAY_URL_PACK_DOC_30))
    kb.add(types.InlineKeyboardButton("🔍 20 анализов • 149 ₽", url=PAY_URL_PACK_ANALYZE_20))
    kb.add(types.InlineKeyboardButton("🔍 100 анализов • 499 ₽", url=PAY_URL_PACK_ANALYZE_100))
    return kb

# Вынесем определение включённых лимитов по активному тарифу
def _included_limits_for(chat_id: int) -> dict:
    info = user_tariffs.get(chat_id)
    if not info:
        return {"photos": 0, "docs": 0, "analysis": 0}
    tariff_key = info["tariff"]
    tariff = TARIFFS.get(tariff_key, {})
    return tariff.get("media_limits", {"photos": 0, "docs": 0, "analysis": 0})

# Проверка и инициализация баланса на месяц (если нет — поставим из тарифа)
def ensure_month_balance(chat_id: int):
    defaults = _included_limits_for(chat_id)
    return get_or_init_month_balance(chat_id, defaults)

# Мягкая проверка лимитов с учётом триала (по 1 штуке, если нет тарифа)
def try_consume(chat_id: int, kind: str) -> bool:
    # если есть активный тариф — работаем с месячным балансом
    if user_tariffs.get(chat_id):
        ensure_month_balance(chat_id)
        return dec_media(chat_id, kind, 1)
    # нет тарифа — триал
    trials = read_trials(chat_id)
    if kind == "photos" and trials["photo_used"] == 0:
        mark_trial_used(chat_id, "photos")
        return True
    if kind == "docs" and trials["doc_used"] == 0:
        mark_trial_used(chat_id, "docs")
        return True
    if kind == "analysis" and trials["analysis_used"] == 0:
        mark_trial_used(chat_id, "analysis")
        return True
    return False

# Сообщение об исчерпании
def out_of_limit_text(kind: str) -> str:
    m = {
        "photos": "генерации фото",
        "docs": "создания документа",
        "analysis": "анализа фото",
    }[kind]
    return f"🚫 Лимит {m} исчерпан. Оформи тариф или докупи пакет 👇"

# --- Точка входа из главного меню: команда «Мультимедиа» ---

@bot.message_handler(func=lambda msg: msg.text == "🎨 Мультимедиа")
def open_multimedia(m):
    bot.send_message(m.chat.id, "Выбери функцию:", reply_markup=multimedia_menu())

@bot.callback_query_handler(func=lambda call: call.data == "mm_buy")
def on_buy(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "Дополнительные пакеты:", reply_markup=multimedia_buy_menu())

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
        # лимит на фото
        if not try_consume(m.chat.id, "photos"):
            bot.send_message(m.chat.id, out_of_limit_text("photos"), reply_markup=multimedia_buy_menu())
            user_media_state.pop(m.chat.id, None)
            return
        # генерация фото
        prompt = m.text.strip()
        try:
            result = client.images.generate(
                model=IMAGE_MODEL,
                prompt=prompt,
                size="1024x1024",
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
        if not try_consume(m.chat.id, "docs"):
            bot.send_message(m.chat.id, out_of_limit_text("docs"), reply_markup=multimedia_buy_menu())
            user_media_state.pop(m.chat.id, None)
            return
        pdf_bytes = make_pdf(m.text or "")
        bot.send_document(m.chat.id, document=io.BytesIO(pdf_bytes), visible_file_name="document.pdf", caption="PDF готов ✅")
        user_media_state.pop(m.chat.id, None)
        return

    if mode == "excel":
        if not try_consume(m.chat.id, "docs"):
            bot.send_message(m.chat.id, out_of_limit_text("docs"), reply_markup=multimedia_buy_menu())
            user_media_state.pop(m.chat.id, None)
            return
        xlsx_bytes = make_excel(m.text or "")
        bot.send_document(m.chat.id, document=io.BytesIO(xlsx_bytes), visible_file_name="data.xlsx", caption="Excel готов ✅")
        user_media_state.pop(m.chat.id, None)
        return

    if mode == "pptx":
        if not try_consume(m.chat.id, "docs"):
            bot.send_message(m.chat.id, out_of_limit_text("docs"), reply_markup=multimedia_buy_menu())
            user_media_state.pop(m.chat.id, None)
            return
        pptx_bytes = make_pptx(m.text or "")
        bot.send_document(m.chat.id, document=io.BytesIO(pptx_bytes), visible_file_name="slides.pptx", caption="Презентация готова ✅")
        user_media_state.pop(m.chat.id, None)
        return

# --- Приём фото для анализа ---

@bot.message_handler(content_types=["photo"])
def on_photo_message(m):
    state = user_media_state.get(m.chat.id, {})
    if state.get("mode") != "photo_analyze":
        return  # не ждём фото — игнорируем, отработает общий fallback

    if not try_consume(m.chat.id, "analysis"):
        bot.send_message(m.chat.id, out_of_limit_text("analysis"), reply_markup=multimedia_buy_menu())
        user_media_state.pop(m.chat.id, None)
        return

    try:
        file_id = m.photo[-1].file_id
        file_info = bot.get_file(file_id)
        url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        img_resp = requests.get(url, timeout=30)
        img_resp.raise_for_status()
        img_b64 = base64.b64encode(img_resp.content).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{img_b64}"

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
