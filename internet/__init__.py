from __future__ import annotations

from typing import List

from openai_adapter import extract_response_text, prepare_responses_input
from settings import CHAT_MODEL, SYSTEM_PROMPT, client
from text_utils import sanitize_model_output

__all__ = ["ask_gpt_web"]


_WEB_SEARCH_PROMPT = (
    f"{SYSTEM_PROMPT}\n\n"
    "Ты работаешь с доступом к интернету. Используй инструмент web_search, когда нужно проверить факты, "
    "найти свежие данные или подтвердить информацию. Сначала кратко сформулируй ответ своими словами, "
    "затем перечисли ключевые факты и закончи разделом 'Источники' со списком ссылок. Отвечай на языке "
    "запроса пользователя."\n"
)


def ask_gpt_web(query: str) -> str:
    """Return an internet-backed answer using the Responses API web_search tool."""

    messages: List[dict] = [
        {"role": "system", "content": _WEB_SEARCH_PROMPT},
        {"role": "user", "content": query},
    ]

    response = client.responses.create(
        model=CHAT_MODEL,
        input=prepare_responses_input(messages),
        response_format={"type": "text"},
        tools=[{"type": "web_search"}],
    )
    text = extract_response_text(response)
    return sanitize_model_output(text)
