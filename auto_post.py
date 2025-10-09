"""Автопостинг для каналов Syntera: разнообразные и актуальные публикации."""

from __future__ import annotations

import base64
import json
import random
import traceback
from collections import deque
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from telebot import types

from openai_adapter import extract_response_text, prepare_responses_input
from settings import OWNER_ID, bot, client as openai_client, CHAT_MODEL, IMAGE_MODEL
 codex/restore-subscription-function-and-posts-qud580
from PIL import Image, UnidentifiedImageError
=======
 main

CHANNEL_ID = "@SynteraAI"
GROUP_ID = "@HubConsult"
BOT_LINK = "https://t.me/SynteraGPT_bot"

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
_recent_news_topics: deque[str] = deque(maxlen=12)
 codex/restore-subscription-function-and-posts-qud580


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


=======


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


 main
def _generate_post_payload(mode: str) -> Tuple[str, str]:
    scenario = _pick_scenario()
    today = datetime.now().strftime("%d.%m.%Y")
    length_instruction = {
        "short": "Создай лаконичный, живой пост, который ощущается коротким — выбирай длину сам, но избегай однообразия.",
        "long": "Создай развёрнутый пост с плавным развитием мысли. Делай его детальным и атмосферным без строгих ограничений по длине.",
    }.get(mode, "Создай сбалансированный пост с богатой подачей и свободной длиной.")
 codex/restore-subscription-function-and-posts-qud580

    system_prompt = (
        "Ты — креативный редактор Telegram-канала SynteraGPT. Каждый текст уникален, "
        "играет с интонациями и подчеркивает выгоды бота. Вставляй максимум два эмодзи, если они усиливают подачу, "
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

=======

    system_prompt = (
        "Ты — креативный редактор Telegram-канала SynteraGPT. Каждый текст уникален, "
        "играет с интонациями и подчеркивает выгоды бота. Вставляй максимум два эмодзи, если они усиливают подачу, "
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

 main
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
        content = response.choices[0].message.content if response.choices else ""
        return _parse_json_payload(content)
    except Exception as exc:  # noqa: BLE001
        print("[POSTGEN] Ошибка генерации текста:", exc)
        if mode == "short":
            return (
                "SynteraGPT всегда под рукой, чтобы подсказать идею, подготовить текст или накидать код. "
                "Подписывайся на AI Systems, заглядывай в Hubconsult и загляни к боту, когда нужна помощь!",
                DEFAULT_IMAGE_PROMPT,
            )
        return (
            (
                "SynteraGPT помогает решать задачи в пару кликов: ищет факты онлайн, анализирует документы, пишет код и держит в тонусе. "
                "В AI Systems делимся уникальными материалами, в Hubconsult обсуждаем идеи. Переходи к боту и оцени мощь GPT-5!"
            ),
            DEFAULT_IMAGE_PROMPT,
        )


def _generate_news_payload() -> Tuple[str, str, str]:
    today = datetime.now().strftime("%d.%m.%Y")
    avoided_topics = ", ".join(_recent_news_topics) or "нет"
    system_prompt = (
        "Ты — редактор новостного канала SynteraGPT. Используй инструмент web_search, чтобы находить свежие новости "
        "об искусственном интеллекте, технологиях и программировании по всему миру. Стремись выбирать темы, которых ещё не было."
    )
    user_prompt = (
        f"Сегодня {today}. Найди актуальный материал об ИИ, технологиях или программировании. "
        f"Избегай повторов тем: {avoided_topics}.\n"
        "Если действительно свежих новостей нет, возьми важную публикацию последней недели и расскажи о ней как об уже состоявшемся событии с выводами.\n"
        "Пост должен вдохновлять подписаться на AI Systems и вступить в Hubconsult, а также приглашать перейти к боту SynteraGPT.\n"
        "Ответь в JSON с полями: post, image_prompt, headline."
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
            max_output_tokens=650,
            temperature=0.8,
            presence_penalty=0.3,
 codex/restore-subscription-function-and-posts-qud580
        )
        payload = extract_response_text(response)
        text, image_prompt = _parse_json_payload(payload)
        data = json.loads(payload)
        headline = (data.get("headline") or text[:80]).strip()
        if headline:
            _recent_news_topics.append(headline.lower())
        return text, image_prompt, headline
    except Exception as exc:  # noqa: BLE001
        print("[POSTGEN] Ошибка генерации новостного поста:", exc)
        return (
            "Сегодня мы разобрали заметную новость из мира ИИ: компании по всему миру внедряют умных ассистентов, "
            "а SynteraGPT помогает опробовать такие решения бесплатно. Подписывайтесь на AI Systems, обсуждайте свежие кейсы в Hubconsult и жмите на бота!",
            DEFAULT_IMAGE_PROMPT,
            "fallback",
        )


def _normalize_image(image_bytes: bytes) -> Optional[bytes]:
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            if img.mode not in {"RGB", "L"}:
                img = img.convert("RGB")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=90, optimize=True)
            return buffer.getvalue()
    except (UnidentifiedImageError, OSError):
        return None
=======
        )
        payload = extract_response_text(response)
        text, image_prompt = _parse_json_payload(payload)
        data = json.loads(payload)
        headline = (data.get("headline") or text[:80]).strip()
        if headline:
            _recent_news_topics.append(headline.lower())
        return text, image_prompt, headline
    except Exception as exc:  # noqa: BLE001
        print("[POSTGEN] Ошибка генерации новостного поста:", exc)
        return (
            "Сегодня мы разобрали заметную новость из мира ИИ: компании по всему миру внедряют умных ассистентов, "
            "а SynteraGPT помогает опробовать такие решения бесплатно. Подписывайтесь на AI Systems, обсуждайте свежие кейсы в Hubconsult и жмите на бота!",
            DEFAULT_IMAGE_PROMPT,
            "fallback",
        )
 main


def _generate_image_bytes(image_prompt: str) -> Optional[bytes]:
    prompt = image_prompt or DEFAULT_IMAGE_PROMPT
 codex/restore-subscription-function-and-posts-qud580
    raw_bytes: Optional[bytes] = None
=======
 main
    try:
        result = openai_client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            size="1792x1024",
            quality="standard",
        )
        b64 = result.data[0].b64_json
 codex/restore-subscription-function-and-posts-qud580
        raw_bytes = base64.b64decode(b64)
    except Exception as exc:  # noqa: BLE001
        print("[POSTGEN] Ошибка генерации картинки:", exc)
    if raw_bytes:
        normalized = _normalize_image(raw_bytes)
        if normalized:
            return normalized
    try:
        with FALLBACK_IMAGE.open("rb") as backup:
            raw_bytes = backup.read()
            return _normalize_image(raw_bytes)
    except FileNotFoundError:
        return None
=======
        return base64.b64decode(b64)
    except Exception as exc:  # noqa: BLE001
        print("[POSTGEN] Ошибка генерации картинки:", exc)
        try:
            with FALLBACK_IMAGE.open("rb") as backup:
                return backup.read()
        except FileNotFoundError:
            return None
 main


def _publish_post(message, caption: str, image_bytes: Optional[bytes]) -> None:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Перейти к боту", url=BOT_LINK))

    targets = [CHANNEL_ID, GROUP_ID]
    try:
        for target in targets:
            if image_bytes:
                buffer = BytesIO(image_bytes)
                buffer.name = "syntera_post.jpg"
 codex/restore-subscription-function-and-posts-qud580
                buffer.seek(0)
=======
 main
                bot.send_photo(
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
        bot.reply_to(message, "✅ Пост опубликован в канал и группу.")
    except Exception as exc:  # noqa: BLE001
        bot.reply_to(message, f"❌ Ошибка при публикации: {exc}")
        traceback.print_exc()


def _handle_post_request(message, mode: str) -> None:
    user_id = getattr(message.from_user, "id", None)
    if user_id != OWNER_ID:
        bot.reply_to(message, "⛔ Команда доступна только владельцу.")
        return

    if mode == "news":
        progress = bot.reply_to(message, "⏳ Собираю свежие новости и оформляю пост...")
        caption, image_prompt, _ = _generate_news_payload()
    else:
        descriptor = "короткий" if mode == "short" else "длинный"
        progress = bot.reply_to(message, f"⏳ Генерирую {descriptor} пост...")
        caption, image_prompt = _generate_post_payload(mode)

    image_bytes = _generate_image_bytes(image_prompt)
    if not image_bytes:
        bot.reply_to(message, "⚠️ Не удалось подготовить изображение — публикация отменена.")
        return

    _publish_post(progress or message, caption, image_bytes)


@bot.message_handler(commands=["post"])
def cmd_post(message):
    args = (message.text or "").split()
    mode = "long"
    if len(args) > 1:
        suffix = args[1].lower()
        if suffix in {"short", "long", "news"}:
            mode = suffix
    _handle_post_request(message, mode)


@bot.message_handler(commands=["post_long"])
def cmd_post_long(message):
    _handle_post_request(message, "long")


@bot.message_handler(commands=["post_short"])
def cmd_post_short(message):
    _handle_post_request(message, "short")


@bot.message_handler(commands=["post_news"])
def cmd_post_news(message):
    _handle_post_request(message, "news")
