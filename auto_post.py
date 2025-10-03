from io import BytesIO
import base64
import traceback

from telebot import types

from settings import bot, OWNER_ID, client as openai_client, CHAT_MODEL
from openai_adapter import extract_response_text

CHANNEL_ID = "@SynteraAI"
GROUP_ID = "@HubConsult"
BOT_LINK = "https://t.me/SynteraGPT_bot"


def _generate_post_text(mode: str = "long") -> str:
    try:
        if mode == "short":
            prompt = (
                "Сделай короткий рекламный пост (2–3 предложения) для Telegram-канала о чат-боте SynteraGPT.\n"
                "- подчеркни GPT-5 интеллект, быстрые ответы, анализ фото/документов\n"
                "- добавь ссылку: https://t.me/SynteraGPT_bot\n"
                "- стиль живой, допускается 1 эмодзи, без хэштегов\n"
            )
        else:
            prompt = (
                "Сделай рекламный пост (4–5 предложений) для Telegram-канала о чат-боте SynteraGPT.\n"
                "- подчеркни возможности: GPT-5 интеллект, быстрые ответы, анализ фото и документов, "
                "создание кода, глубокие исследования\n"
                "- укажи, что есть доступ к интернету, историческим данным, Википедии, Google и другим источникам\n"
                "- упомяни преимущества ИИ и пару строк про новости или тенденции искусственного интеллекта\n"
                "- добавь ссылку на бота: https://t.me/SynteraGPT_bot\n"
                "- стиль информативный, допускается 1–2 эмодзи, без хэштегов\n"
                "- итог до 700 символов\n"
            )

        resp = openai_client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "text"},
            max_completion_tokens=400,
        )
        return extract_response_text(resp).strip()
    except Exception as exc:
        print("[POSTGEN] Ошибка GPT:", exc)
        return (
            "SynteraGPT — умный AI-бот на базе GPT-5. "
            "Быстро отвечает, анализирует фото и документы, создаёт код и делает глубокие исследования. "
            "Поддерживает доступ к интернету, Википедии и историческим данным. "
            "Всегда в курсе новостей искусственного интеллекта.\n\n"
            "👉 Попробуй: https://t.me/SynteraGPT_bot"
        )


def _generate_post_image():
    try:
        img_prompt = (
            "Футуристичный баннер для Telegram-канала про чат-бота SynteraGPT. "
            "Тёмный космос, знак бесконечности ∞ в неоновом стиле, "
            "современные акценты искусственного интеллекта, высокое качество."
        )
        result = openai_client.images.generate(
            model="gpt-image-1",
            prompt=img_prompt,
            size="1280x720",
        )
        b64 = result.data[0].b64_json
        img_bytes = base64.b64decode(b64)
        return BytesIO(img_bytes)
    except Exception as exc:
        print("[POSTGEN] Ошибка генерации картинки:", exc)
        return None


@bot.message_handler(commands=["post"])
def cmd_post(message):
    user_id = getattr(message.from_user, "id", None)
    if user_id != OWNER_ID:
        bot.reply_to(message, "⛔ Команда доступна только владельцу.")
        return

    args = message.text.split()
    mode = "long"
    if len(args) > 1 and args[1].lower() == "short":
        mode = "short"

    bot.reply_to(message, f"⏳ Генерирую {('короткий' if mode == 'short' else 'длинный')} пост...")

    caption = _generate_post_text(mode)
    img = _generate_post_image()

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Перейти к боту", url=BOT_LINK))

    try:
        for target in [CHANNEL_ID, GROUP_ID]:
            if img:
                bot.send_photo(
                    target,
                    img,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            else:
                bot.send_message(
                    target,
                    caption,
                    parse_mode="HTML",
                    reply_markup=kb,
                )
        bot.reply_to(message, "✅ Пост опубликован в канал и группу.")
    except Exception as exc:
        bot.reply_to(message, f"❌ Ошибка при публикации: {exc}")
        traceback.print_exc()
