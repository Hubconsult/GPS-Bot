"""Автопостинг контента для каналов Syntera."""

from __future__ import annotations

import base64
import json
import random
import traceback
from contextlib import suppress
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, UnidentifiedImageError
from telebot import types

from openai_adapter import extract_response_text, prepare_responses_input
from settings import (
    CHAT_MODEL,
    OWNER_ID,
    bot,
    client as openai_client,
)

CHANNEL_ID = "@SynteraAI"
GROUP_ID = "@HubConsult"
BOT_LINK = "https://t.me/SynteraGPT_bot"
BANER_PATH = Path(__file__).resolve().parent / "baner_dlya_perehoda.png"

SCENARIOS = [
    "Расскажи мини-историю предпринимателя, который с помощью бота ускорил запуск продукта",
    "Сфокусируйся на свежей истории успеха из мира искусственного интеллекта и свяжи её с возможностями SynteraGPT",
    "Опиши, как команда аналитиков использует бота для глубоких исследований и подготовки отчётов",
    "Представь, что пользователь ищет нестандартные идеи для контента и находит их через SynteraGPT",
    "Сделай акцент на экспертной поддержке сообщества AI Systems и живом общении в Hubconsult",
    "Покажи, как SynteraGPT помогает автоматизировать рутинные задачи специалиста по маркетингу",
    "Опиши утро человека, который экономит время благодаря быстрым ответам и поиску с SynteraGPT",
]

DEFAULT_IMAGE_PROMPT = (
    "Футуристичный баннер для Telegram-поста о SynteraGPT: неоновые акценты, технологии, "
    "дружественная атмосфера, современный стиль."
)
FALLBACK_IMAGE = Path(__file__).resolve().parent / "syntera_logo.png"

_last_scenario: Optional[str] = None


def _pick_scenario() -> str:
    global _last_scenario

    scenario = random.choice(SCENARIOS)
    if _last_scenario and len(SCENARIOS) > 1:
        attempts = 0
        while scenario == _last_scenario and attempts < 5:
            scenario = random.choice(SCENARIOS)
            attempts += 1
    _last_scenario = scenario
    return scenario


def _parse_json_payload(raw: str) -> Tuple[str, str]:
    data = json.loads(raw)
    post_text = (data.get("post") or "").strip()
    image_prompt = (data.get("image_prompt") or "").strip()
    if not post_text:
        raise ValueError("Empty post text")
    return post_text, image_prompt


def _generate_post_payload(mode: str) -> Tuple[str, str]:
    scenario = _pick_scenario()
    today = datetime.now().strftime("%d.%m.%Y")
    length_instruction = {
        "short": "Создай лаконичный, живой пост, который ощущается коротким — выбирай длину сам, но избегай однообразия.",
        "long": "Создай развёрнутый пост с плавным развитием мысли. Делай его детальным и атмосферным без строгих ограничений по длине.",
    }.get(mode, "Создай сбалансированный пост с богатой подачей и свободной длиной.")

    system_prompt = (
        "Ты — креативный редактор Telegram-канала SynteraGPT. Каждый текст уникален, "
        "играет с интонациями и подчёркивает выгоды бота. Вставляй максимум два эмодзи, если они усиливают подачу, "
        "но не делай это обязательным."
    )

    user_prompt = (
        f"Сегодня {today}. {length_instruction}\n"
        f"Используй как вдохновение: {scenario}.\n"
        "Расскажи, чем полезен SynteraGPT: доступ к интернету, анализ фото и документов, генерация кода, быстрые ответы.\n"
        "Обязательно упомяни, что эксклюзивные материалы публикуются в канале AI Systems и в группе Hubconsult.\n"
        f"Добавь естественный призыв перейти к боту по ссылке {BOT_LINK}.\n"
        "Меняй структуру, чтобы каждый пост отличался от предыдущего.\n"
        "Ответь строго в формате JSON с полями post и image_prompt."
    )

    try:
        response = openai_client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_completion_tokens=500,
            temperature=0.85,
            presence_penalty=0.4,
            frequency_penalty=0.25,
        )
        payload = extract_response_text(response)
        return _parse_json_payload(payload)
    except Exception as exc:  # noqa: BLE001
        print("[POSTGEN] Ошибка генерации текста:", exc)
        if mode == "short":
            return (
                "SynteraGPT всегда под рукой, чтобы подсказать идею, подготовить текст или накидать код. "
                "Подписывайся на AI Systems, заглядывай в Hubconsult и заходи к боту, когда нужна помощь!",
                DEFAULT_IMAGE_PROMPT,
            )
        return (
            (
                "SynteraGPT помогает решать задачи в пару кликов: ищет факты онлайн, анализирует документы, пишет код и держит в тонусе. "
                "Подписывайся на канал AI Systems, обсуждай свежие кейсы в Hubconsult и переходи к боту SynteraGPT прямо сейчас!"
            ),
            DEFAULT_IMAGE_PROMPT,
        )


def _generate_news_payload() -> tuple[str, str, str]:
    """Генерирует развёрнутую новость из открытых источников с реальной ссылкой."""

    today = datetime.now().strftime("%d.%m.%Y")

    system_prompt = (
        "Ты — редактор Telegram-канала SynteraGPT. "
        "Используй инструмент web_search, чтобы находить реальные новости об ИИ, технологиях и нейросетях. "
        "Выбирай свежую, проверенную публикацию из авторитетных источников (Reuters, MIT Tech Review, Wired, The Verge, N+1, TAdviser и др.). "
        "Создай развёрнутый материал — 4–8 абзацев — с объяснением сути, контекста, последствий и мнений экспертов. "
        "Обязательно укажи ссылку на источник (в поле url). Не выдумывай новости."
    )

    user_prompt = (
        f"Сегодня {today}. Найди самую интересную и важную новость о технологиях, искусственном интеллекте или науке. "
        "Составь развёрнутый текст, оформи как профессиональную статью для Telegram-канала. "
        "Добавь в конце ссылку на оригинальный источник. "
        "Ответь строго в формате JSON с полями: headline, post, url."
    )

    try:
        response = openai_client.responses.create(
            model=CHAT_MODEL,
            input=prepare_responses_input(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            ),
            tools=[{"type": "web_search"}],
            response_format={"type": "json_object"},
            max_output_tokens=2000,
            temperature=0.75,
        )

        payload = extract_response_text(response)
        data = json.loads(payload)

        headline = (data.get("headline") or "Новости технологий").strip()
        post_text = (data.get("post") or "").strip()
        news_url = (data.get("url") or "").strip()

        if not news_url.startswith("http"):
            raise ValueError("URL не найден")

        print(f"[NEWS] Источник: {news_url}")

        return headline, post_text, news_url

    except Exception as exc:  # noqa: BLE001
        print("[POSTGEN] Ошибка при поиске новости:", exc)
        return (
            "SynteraGPT | Новости технологий",
            (
                "Сегодня SynteraGPT продолжает делиться свежими событиями из мира искусственного интеллекта и инноваций. "
                "Следите за нашими публикациями, чтобы узнавать первыми о новых возможностях ИИ и технологиях будущего."
            ),
            "https://synteragpt.ai/news",
        )


def _normalize_image(image_bytes: bytes) -> Optional[bytes]:
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            if img.mode not in {"RGB", "L"}:
                img = img.convert("RGB")
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=90, optimize=True)
            return buffer.getvalue()
    except (UnidentifiedImageError, OSError):
        return None


def _generate_image_bytes(image_prompt: str) -> Optional[bytes]:
    prompt = image_prompt or DEFAULT_IMAGE_PROMPT
    try:
        result = openai_client.images.generate(
            prompt=prompt,
            size="512x512",  # уменьшенный размер
            quality="standard",
        )
        b64 = None
        if result.data and len(result.data) > 0:
            b64 = result.data[0].b64_json
        if not b64:
            raise ValueError("Empty b64 data from API")

        raw = base64.b64decode(b64)
        if not raw or len(raw) < 10240:
            raise ValueError(f"Image too small: {len(raw)} bytes")

        normalized = _normalize_image(raw)
        if normalized:
            return normalized
        return raw
    except Exception as exc:  # noqa: BLE001
        print(f"[POSTGEN] Ошибка генерации картинки: {exc}")
        try:
            with FALLBACK_IMAGE.open("rb") as f:
                fb = f.read()
            return _normalize_image(fb) or fb
        except Exception as e2:  # noqa: BLE001
            print(f"[POSTGEN] Fallback тоже не удался: {e2}")
            return None


def _publish_post(message, caption: str, image_bytes: Optional[bytes]) -> None:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Перейти к боту", url=BOT_LINK))

    targets = [CHANNEL_ID, GROUP_ID]
    for target in targets:
        if image_bytes:
            buffer = BytesIO(image_bytes)
            buffer.name = "syntera_post.jpg"
            buffer.seek(0)
            try:
                bot.send_photo(
                    target,
                    buffer,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            except Exception as e_photo:  # noqa: BLE001
                print(f"[POSTGEN] send_photo failed, try send_document: {e_photo}")
                buffer.seek(0)
                bot.send_document(
                    target,
                    buffer,
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
    try:
        bot.reply_to(message, "✅ Пост опубликован.")
    except Exception:  # noqa: BLE001
        pass


def _handle_post_request(message, mode: str) -> None:
    user_id = getattr(message.from_user, "id", None)
    if user_id != OWNER_ID:
        bot.reply_to(message, "⛔ Команда доступна только владельцу.")
        return

    status_msg = bot.reply_to(message, "🧠 Генерирую контент, это займёт несколько секунд…")
    caption = ""
    image_bytes: Optional[bytes] = None

    try:
        if mode == "news":
            headline, post_text, news_url = _generate_news_payload()
            caption = (
                f"<b>{headline}</b>\n\n"
                f"{post_text}\n\n"
                f"🔗 Источник: <a href='{news_url}'>{news_url}</a>\n\n"
                f"Подписывайся на канал AI Systems и участвуй в обсуждениях Hubconsult!"
            )
            if BANER_PATH.exists():
                with BANER_PATH.open("rb") as f:
                    image_bytes = f.read()
        else:
            text, image_prompt = _generate_post_payload(mode)
            caption = text
            image_bytes = _generate_image_bytes(image_prompt)

        _publish_post(message, caption, image_bytes)
    except Exception as exc:  # noqa: BLE001
        bot.reply_to(message, f"❌ Не удалось создать пост: {exc}")
        traceback.print_exc()
    finally:
        with suppress(Exception):
            bot.delete_message(status_msg.chat.id, status_msg.message_id)


@bot.message_handler(commands=["post_short"])
def create_short_post(message):
    _handle_post_request(message, "short")


@bot.message_handler(commands=["post_long"])
def create_long_post(message):
    _handle_post_request(message, "long")


@bot.message_handler(commands=["post_news"])
def create_news_post(message):
    _handle_post_request(message, "news")


__all__ = [
    "create_short_post",
    "create_long_post",
    "create_news_post",
]
